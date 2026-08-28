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
        cls.designation = cls.env["hjig.governance.designation"].create({
            "code": "GATE-AUTH", "name": "Gate Authority", "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.stage = cls.env["hjig.launchguard.stage"].create({
            "code": "TEST-B3", "name": "Test Steel Gate", "sequence": 3, "stage_type": "technical_gate",
        })
        cls.template = cls.env["hjig.checklist.template"].create({
            "code": "TEST-B3-READINESS", "name": "Test B3 Readiness", "version": "1.0",
            "stage_id": cls.stage.id, "purpose": "Verify readiness without duplicate data entry.",
            "owner_designation_id": cls.designation.id,
            "item_ids": [(0, 0, {
                "item_code": "B3-01", "title": "Steel approval evidence",
                "instruction": "Read the approved steel record and confirm evidence.",
                "blocking": True, "evidence_required": True, "source_record_type": "live_record",
            })],
        })

    def _target(self):
        return "project.project,%s" % self.project.id

    def test_checklist_cannot_pass_without_evidence(self):
        checklist = self.env["hjig.checklist"].create({
            "project_id": self.project.id, "target_ref": self._target(), "template_id": self.template.id,
        })
        self.assertEqual(len(checklist.response_ids), 1)
        with self.assertRaises(ValidationError):
            checklist.response_ids.action_pass()
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

    def test_gate_go_requires_ready_checklist_and_human_approval(self):
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": "Steel approval", "source_party": "hongyi",
            "source_url": "https://drive.google.com/steel-approval",
        })
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
