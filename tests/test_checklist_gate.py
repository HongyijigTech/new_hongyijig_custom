import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from psycopg2.errors import UniqueViolation


@tagged("post_install", "-at_install")
class TestChecklistGate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = cls.env["res.users"].create({
            "name": "Gate Requester", "login": "gate.requester@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Gate Approver", "login": "gate.approver@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id, cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Gate Project", "hjig_authorized_user_ids": [(6, 0, [cls.requester.id, cls.approver.id])],
        })
        cls.designation = cls.env.ref("new_hongyijig_custom.designation_project_coordinator")
        cls.designation.holder_ids = [(4, cls.approver.id)]
        cls.stage = cls.env.ref("new_hongyijig_custom.stage_pa00")
        cls.template = cls.env.ref("new_hongyijig_custom.checklist_template_pa00")

    def _target(self):
        return "project.project,%s" % self.project.id

    def _ready_gate(self, stage, project=None, cycle=1):
        project = project or self.project
        gate = self.env["hjig.gate"].create({
            "project_id": project.id,
            "target_ref": "project.project,%s" % project.id,
            "stage_id": stage.id,
            "cycle": cycle,
            "approval_authority_designation_id": self.designation.id,
        })
        gate.action_load_stage_checklist()
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": project.id,
            "target_ref": "project.project,%s" % project.id,
            "evidence_type": "%s cycle %s readiness" % (stage.code, cycle),
            "source_party": "hongyi",
            "source_url": "https://drive.google.com/%s-%s-%s" % (project.id, stage.code, cycle),
        })
        evidence.with_user(self.approver).action_accept()
        checklist = gate.checklist_ids
        checklist.action_start()
        checklist.response_ids.evidence_ids = [(6, 0, [evidence.id])]
        checklist.response_ids.action_pass()
        checklist.action_mark_ready()
        return gate

    def test_checklist_cannot_pass_without_evidence(self):
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(), "template_id": self.template.id,
        })
        self.assertEqual(len(checklist.response_ids), 1)
        with self.assertRaises(ValidationError):
            checklist.response_ids.action_pass()
        with self.assertRaises(ValidationError):
            checklist.response_ids.action_fail()
        with self.assertRaises(ValidationError):
            checklist.action_mark_ready()

    def test_operating_catalogue_covers_every_governance_stage(self):
        expected_codes = {
            "PA-00-READINESS", "TG-01-READINESS", "TG-02-READINESS", "TG-03-READINESS",
            "TG-04-READINESS", "TG-05-READINESS", "TG-06-READINESS", "TG-07-READINESS",
            "TG-08-READINESS", "TG-09-READINESS",
        }
        templates = self.env["hjig.checklist.template"].search([("code", "in", list(expected_codes))])
        self.assertEqual(set(templates.mapped("code")), expected_codes)
        self.assertTrue(all(template.item_ids for template in templates))

    def test_gate_loads_the_single_active_stage_checklist(self):
        gate = self.env["hjig.gate"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "stage_id": self.stage.id, "approval_authority_designation_id": self.designation.id,
        })
        gate.action_load_stage_checklist()
        self.assertEqual(len(gate.checklist_ids), 1)
        self.assertEqual(gate.checklist_ids.template_id, self.template)
        self.assertEqual(len(gate.checklist_ids.response_ids), len(self.template.item_ids))
        with self.assertRaises(UserError):
            gate.action_load_stage_checklist()
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env["hjig.checklist"].create({
                "project_id": self.project.id, "target_ref": self._target(),
                "template_id": self.template.id, "gate_id": gate.id,
            })

    def test_gate_decisions_cannot_skip_the_next_programme_stage(self):
        future_stage = self.env.ref("new_hongyijig_custom.stage_tg02")
        gate = self.env["hjig.gate"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "stage_id": future_stage.id,
            "approval_authority_designation_id": self.designation.id,
        })
        with self.assertRaises(ValidationError):
            gate.action_request_decision()

    def test_draft_gate_identity_is_immutable_after_creation(self):
        gate = self.env["hjig.gate"].create({
            "project_id": self.project.id,
            "target_ref": self._target(),
            "stage_id": self.stage.id,
            "approval_authority_designation_id": self.designation.id,
        })
        for values in (
            {"stage_id": self.env.ref("new_hongyijig_custom.stage_tg01").id},
            {"cycle": 2},
            {"approval_authority_designation_id": False},
        ):
            with self.assertRaises(ValidationError):
                gate.write(values)
        self.assertEqual(gate.stage_id, self.stage)
        self.assertEqual(gate.cycle, 1)

    def test_parallel_pending_gate_cycles_are_blocked_and_recoverable(self):
        first = self._ready_gate(self.stage, cycle=1)
        second = self._ready_gate(self.stage, cycle=2)
        first.with_user(self.requester).action_request_decision()
        cancelled_approval = first.approval_id
        with self.assertRaises(ValidationError):
            second.with_user(self.requester).action_request_decision()
        first.decision_notes = "Duplicate request opened before the first decision completed."
        first.action_cancel_pending_decision()
        self.assertEqual(first.state, "draft")
        self.assertEqual(cancelled_approval.state, "cancelled")
        second.with_user(self.requester).action_request_decision()
        self.assertEqual(second.state, "pending")

    def test_approved_gate_decision_cannot_be_cancelled(self):
        gate = self._ready_gate(self.stage)
        gate.with_user(self.requester).action_request_decision()
        approval = gate.approval_id
        approval.with_user(self.approver).action_approve()
        gate.decision_notes = "Attempted cancellation after approval."
        with self.assertRaises(UserError):
            gate.action_cancel_pending_decision()
        self.assertEqual(approval.state, "approved")
        self.assertEqual(approval.approver_id, self.approver)

    def test_rejected_gate_decision_cannot_be_cancelled(self):
        gate = self._ready_gate(self.stage)
        gate.with_user(self.requester).action_request_decision()
        approval = gate.approval_id
        approval.decision_reason = "Readiness evidence is not acceptable."
        approval.with_user(self.approver).action_reject()
        gate.decision_notes = "Attempted cancellation after rejection."
        with self.assertRaises(UserError):
            gate.action_cancel_pending_decision()
        self.assertEqual(approval.state, "rejected")
        self.assertEqual(approval.approver_id, self.approver)

    def test_cancelled_gate_approval_cannot_be_decided(self):
        gate = self._ready_gate(self.stage)
        gate.with_user(self.requester).action_request_decision()
        approval = gate.approval_id
        gate.decision_notes = "Duplicate gate request cancelled before decision."
        gate.action_cancel_pending_decision()
        with self.assertRaises(UserError):
            approval.with_user(self.approver).action_approve()
        self.assertEqual(approval.state, "cancelled")
        self.assertEqual(gate.state, "draft")

    def test_gate_decision_can_be_applied_only_once(self):
        gate = self._ready_gate(self.stage)
        gate.with_user(self.requester).action_request_decision()
        gate.approval_id.with_user(self.approver).action_approve()
        gate.action_apply_decision()
        transition_count = self.env["hjig.transition.log"].search_count([
            ("target_ref", "=", "%s,%s" % (gate._name, gate.id)),
            ("decision", "=", "approved"),
        ])
        with self.assertRaises(UserError):
            gate.action_apply_decision()
        self.assertEqual(gate.state, "go")
        self.assertEqual(self.env["hjig.transition.log"].search_count([
            ("target_ref", "=", "%s,%s" % (gate._name, gate.id)),
            ("decision", "=", "approved"),
        ]), transition_count)

    def test_toollock_control_uses_lite_closure_without_installation(self):
        project = self.env["project.project"].create({
            "name": "ToolLock Control Route",
            "hjig_programme": "toollock_control",
            "hjig_authorized_user_ids": [(6, 0, [self.requester.id, self.approver.id])],
        })
        route = ("TG-01", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-09")
        for code in route:
            stage = self.env["hjig.launchguard.stage"].search([("code", "=", code)], limit=1)
            gate = self._ready_gate(stage, project=project)
            if code == "TG-09":
                self.assertEqual(gate.checklist_ids.template_id.code, "TG-09-TOOLLOCK-CONTROL")
                titles = " ".join(gate.checklist_ids.response_ids.mapped("title")).lower()
                self.assertNotIn("installation support is completed", titles)
                self.assertNotIn("site trial and final acceptance", titles)
            gate.with_user(self.requester).action_request_decision()
            gate.approval_id.with_user(self.approver).action_approve()
            gate.action_apply_decision()
        self.assertEqual(project.hjig_current_stage_id.code, "TG-09")

    def test_gate_go_requires_ready_checklist_and_human_approval(self):
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": "Steel approval", "source_party": "hongyi",
            "source_url": "https://drive.google.com/steel-approval",
        })
        evidence.with_user(self.approver).action_accept()
        gate = self.env["hjig.gate"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "stage_id": self.stage.id, "approval_authority_designation_id": self.designation.id,
        })
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "template_id": self.template.id, "gate_id": gate.id,
        })
        checklist.action_start()
        checklist.response_ids.evidence_ids = evidence
        checklist.response_ids.action_pass()
        checklist.action_mark_ready()
        gate.with_user(self.requester).action_request_decision()
        self.assertEqual(gate.state, "pending")
        with self.assertRaises(ValidationError):
            self.env["hjig.checklist"].create({
                "project_id": self.project.id, "target_ref": self._target(),
                "template_id": self.template.id, "gate_id": gate.id,
            })
        unlinked = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(), "template_id": self.template.id,
        })
        with self.assertRaises(ValidationError):
            unlinked.gate_id = gate
        gate.approval_id.with_user(self.approver).action_approve()
        gate.action_apply_decision()
        self.assertEqual(gate.state, "go")
        self.assertEqual(checklist.state, "closed")
        self.assertEqual(self.project.hjig_current_stage_id, self.stage)

    def test_result_evidence_is_locked_and_rework_is_a_new_cycle(self):
        first_evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": "Initial check", "source_party": "hongyi",
            "source_url": "https://drive.google.com/initial-check",
        })
        first_evidence.with_user(self.approver).action_accept()
        second_evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": "Rework check", "source_party": "hongyi",
            "source_url": "https://drive.google.com/rework-check",
        })
        second_evidence.with_user(self.approver).action_accept()
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "template_id": self.template.id,
        })
        response = checklist.response_ids
        response.evidence_ids = first_evidence
        response.with_user(self.approver).action_fail()
        with self.assertRaises(ValidationError):
            response.evidence_ids = [(6, 0, [second_evidence.id])]
        response.rework_reason = "Correct the steel approval evidence."
        response.with_user(self.approver).action_reset_for_rework()
        self.assertEqual(response.cycle, 2)
        self.assertEqual(response.result, "pending")
        response.evidence_ids = [(6, 0, [second_evidence.id])]
        response.with_user(self.approver).action_pass()
        self.assertEqual(response.result, "pass")
        history = json.loads(response.audit_history_json)
        self.assertEqual([entry["cycle"] for entry in history], [1, 2])
        self.assertEqual(history[0]["result"], "fail")
        self.assertEqual(history[0]["evidence"][0]["id"], first_evidence.id)
        self.assertEqual(history[1]["result"], "pass")
        self.assertEqual(history[1]["evidence"][0]["id"], second_evidence.id)

    def test_unaccepted_evidence_cannot_support_checklist_result(self):
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": "Unverified check", "source_party": "hongyi",
            "source_url": "https://drive.google.com/unverified-check",
        })
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "template_id": self.template.id,
        })
        checklist.response_ids.evidence_ids = evidence
        with self.assertRaises(ValidationError):
            checklist.response_ids.with_user(self.approver).action_pass()

    def test_response_create_rejects_forged_controlled_result(self):
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "template_id": self.template.id,
        })
        with self.assertRaises(ValidationError):
            self.env["hjig.checklist.response"].with_user(self.requester).create({
                "checklist_id": checklist.id,
                "template_item_id": self.template.item_ids[:1].id,
                "result": "pass",
                "verified_by_id": self.requester.id,
                "cycle": 9,
                "audit_history_json": '[{"cycle": 9, "result": "pass"}]',
            })
