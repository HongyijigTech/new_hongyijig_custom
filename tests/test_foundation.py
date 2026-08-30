from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHongyiFoundation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = cls.env["res.users"].create({
            "name": "Foundation Requester",
            "login": "foundation.requester@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Foundation Approver",
            "login": "foundation.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Foundation Test Project",
            "date_start": "2026-08-28",
            "hjig_authorized_user_ids": [(6, 0, [cls.requester.id, cls.approver.id])],
        })
        cls.env["project.task"].create({
            "name": "Foundation governed plan task", "project_id": cls.project.id,
            "user_ids": [(6, 0, [cls.requester.id])],
            "planned_date_begin": "2026-08-28 09:00:00", "date_deadline": "2026-08-28 17:00:00",
        })
        cls.designation = cls.env["hjig.governance.designation"].create({
            "code": "FOUNDATION-APPROVER",
            "name": "Foundation Approver",
            "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })

    def _target(self, record=None):
        record = record or self.project
        return "%s,%s" % (record._name, record.id)

    def _baseline(self, revision="R00", **overrides):
        values = {
            "project_id": self.project.id,
            "target_ref": self._target(),
            "baseline_type": "plan",
            "revision": revision,
            "effective_date": "2026-08-28",
            "approval_authority_designation_id": self.designation.id,
        }
        values.update(overrides)
        return self.env["hjig.baseline"].create(values)

    def test_target_must_belong_to_project(self):
        other_project = self.env["project.project"].create({"name": "Other Project"})
        with self.assertRaises(ValidationError):
            self._baseline(target_ref=self._target(other_project))

    def test_runtime_adapters_expose_only_project_resolvable_legacy_records(self):
        selection = dict(self.env["hjig.evidence.link"]._selection_target_model())
        if "hjig.sourcebridge.component" in self.env.registry:
            self.assertIn("hjig.sourcebridge.component", selection)
        for model_name in ("hjig.mould.register", "s.series.risk"):
            if model_name in self.env.registry:
                model = self.env[model_name]
                has_direct_project = any(
                    field_name in model._fields
                    and model._fields[field_name].type == "many2one"
                    and model._fields[field_name].comodel_name == "project.project"
                    for field_name in ("project_id", "x_project_id")
                )
                if not has_direct_project:
                    self.assertNotIn(model_name, selection)

    def test_project_team_record_rule_isolates_foundation_records(self):
        other_project = self.env["project.project"].create({"name": "Restricted Project"})
        other_baseline = self.env["hjig.baseline"].create({
            "project_id": other_project.id,
            "target_ref": self._target(other_project),
            "baseline_type": "plan",
            "revision": "R00",
            "effective_date": "2026-08-28",
            "approval_authority_designation_id": self.designation.id,
        })
        visible = self.env["hjig.baseline"].with_user(self.requester).search_count([
            ("id", "=", other_baseline.id),
        ])
        self.assertEqual(visible, 0)

    def test_baseline_requires_controlled_workflow(self):
        baseline = self._baseline()
        with self.assertRaises(ValidationError):
            baseline.state = "approved"
        with self.assertRaises(ValidationError):
            baseline.with_context(allow_hjig_baseline_workflow=True).write({"state": "approved"})

    def test_project_user_cannot_self_enrol(self):
        with self.assertRaises(UserError):
            self.project.with_user(self.requester).write({
                "hjig_authorized_user_ids": [(4, self.requester.id)],
            })

    def test_baseline_approval_and_supersession(self):
        first = self._baseline()
        first.with_user(self.requester).action_submit_review()
        first.approval_id.with_user(self.approver).action_approve()
        first.action_apply_approval()
        self.assertEqual(first.state, "approved")

        second = self._baseline(revision="R01", supersedes_id=first.id, change_reason="Approved revision")
        second.with_user(self.requester).action_submit_review()
        second.approval_id.with_user(self.approver).action_approve()
        second.action_apply_approval()
        self.assertEqual(first.state, "superseded")
        self.assertEqual(first.superseded_by_id, second)
        self.assertEqual(second.state, "approved")

    def test_requester_cannot_decide_own_approval(self):
        baseline = self._baseline()
        baseline.with_user(self.requester).action_submit_review()
        with self.assertRaises(UserError):
            baseline.approval_id.with_user(self.requester).action_approve()

    def test_rejection_requires_reason(self):
        approval = self.env["hjig.approval"].create({
            "project_id": self.project.id,
            "target_ref": self._target(),
            "approval_type": "other",
            "requested_by_id": self.requester.id,
            "authority_designation_id": self.designation.id,
        })
        with self.assertRaises(ValidationError):
            approval.with_user(self.approver).action_reject()
        approval.decision_reason = "Evidence incomplete"
        approval.with_user(self.approver).action_reject()
        self.assertEqual(approval.state, "rejected")
        self.assertEqual(self.env["hjig.transition.log"].search_count([("approval_id", "=", approval.id)]), 1)

    def test_pending_approval_identity_is_immutable(self):
        approval = self.env["hjig.approval"].create({
            "project_id": self.project.id,
            "target_ref": self._target(),
            "approval_type": "other",
            "requested_by_id": self.requester.id,
            "authority_designation_id": self.designation.id,
        })
        other_designation = self.env["hjig.governance.designation"].create({
            "code": "WRONG-APPROVER",
            "name": "Wrong Approval Authority",
            "category": "governance",
            "holder_ids": [(6, 0, [self.approver.id])],
        })
        for values in (
            {"authority_designation_id": other_designation.id},
            {"approval_type": "gate"},
            {"target_ref": self._target(self.env["project.project"].create({"name": "Wrong Target"}))},
        ):
            with self.assertRaises(ValidationError):
                approval.with_user(self.approver).write(values)
        self.assertEqual(approval.authority_designation_id, self.designation)
        self.assertEqual(approval.approval_type, "other")
        self.assertEqual(approval.target_ref, self.project)

    def test_evidence_requires_a_source(self):
        values = {
            "project_id": self.project.id,
            "target_ref": self._target(),
            "evidence_type": "Customer specification",
            "source_party": "customer",
        }
        with self.assertRaises(ValidationError):
            self.env["hjig.evidence.link"].create(values)
        values["source_url"] = "https://drive.google.com/evidence"
        evidence = self.env["hjig.evidence.link"].create(values)
        evidence.with_user(self.approver).action_accept()
        self.assertEqual(evidence.verification_state, "accepted")
        with self.assertRaises(ValidationError):
            evidence.source_url = "https://drive.google.com/replaced"

    def test_evidence_creator_cannot_verify_own_evidence(self):
        second_approver = self.env["res.users"].create({
            "name": "Independent Evidence Approver",
            "login": "foundation.independent.approver@test.invalid",
            "group_ids": [(6, 0, [
                self.env.ref("project.group_project_user").id,
                self.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        self.project.hjig_authorized_user_ids = [(4, second_approver.id)]
        evidence = self.env["hjig.evidence.link"].with_user(self.approver).create({
            "project_id": self.project.id,
            "target_ref": self._target(),
            "evidence_type": "Creator segregation test",
            "source_party": "hongyi",
            "source_url": "https://drive.google.com/creator-segregation",
        })
        with self.assertRaises(ValidationError):
            evidence.with_user(self.approver).action_accept()
        evidence.with_user(second_approver).action_accept()
        self.assertEqual(evidence.verifier_id, second_approver)

    def test_transition_log_is_append_only(self):
        transition = self.env["hjig.transition.log"].create({
            "project_id": self.project.id,
            "target_ref": self._target(),
            "from_state": "draft",
            "to_state": "review",
            "decision": "submitted",
            "actor_id": self.env.user.id,
        })
        with self.assertRaises(UserError):
            transition.reason = "Changed"
        with self.assertRaises(UserError):
            transition.unlink()

    def test_project_cockpit_actions_are_project_scoped(self):
        cases = [
            ("action_open_hjig_baselines", "hjig.baseline"),
            ("action_open_hjig_sor", "hjig.sor"),
            ("action_open_hjig_gates", "hjig.gate"),
            ("action_open_hjig_tooling", "hjig.tooling.execution"),
            ("action_open_hjig_inspections", "hjig.inspection"),
        ]
        for method_name, model_name in cases:
            action = getattr(self.project, method_name)()
            self.assertEqual(action["res_model"], model_name)
            self.assertIn(("project_id", "=", self.project.id), action["domain"])
            self.assertEqual(action["context"]["default_project_id"], self.project.id)

    def test_project_cockpit_hides_commercial_records_without_role(self):
        with self.assertRaises(UserError):
            self.project.with_user(self.requester).action_open_hjig_commercial_links()

    def test_programme_route_exposes_only_applicable_stages(self):
        design_project = self.env["project.project"].create({
            "name": "LaunchGuard Design Project",
            "hjig_programme": "launchguard_design",
            "hjig_authorized_user_ids": [(6, 0, [self.requester.id, self.approver.id])],
        })
        self.assertEqual(set(design_project.hjig_allowed_stage_ids.mapped("code")), {"PA-00", "TG-01"})
        with self.assertRaises(ValidationError):
            design_project.hjig_current_stage_id = self.env.ref("new_hongyijig_custom.stage_tg02")
        with self.assertRaises(ValidationError):
            self.env["hjig.gate"].create({
                "project_id": design_project.id,
                "target_ref": "project.project,%s" % design_project.id,
                "stage_id": self.env.ref("new_hongyijig_custom.stage_tg02").id,
                "approval_authority_designation_id": self.designation.id,
            })

        lite_project = self.env["project.project"].create({
            "name": "ToolLock Lite Project", "hjig_programme": "toollock_lite",
            "hjig_authorized_user_ids": [(6, 0, [self.requester.id, self.approver.id])],
        })
        self.assertFalse(lite_project.hjig_allowed_stage_ids)

    def test_programme_and_current_stage_reject_direct_writes(self):
        with self.assertRaises(ValidationError):
            self.project.hjig_programme = "launchguard_design"
        with self.assertRaises(ValidationError):
            self.project.hjig_current_stage_id = self.env.ref("new_hongyijig_custom.stage_pa00")

    def test_archived_stage_cannot_receive_a_gate(self):
        stage = self.env.ref("new_hongyijig_custom.stage_pa00")
        stage.active = False
        with self.assertRaises(ValidationError):
            self.env["hjig.gate"].create({
                "project_id": self.project.id,
                "target_ref": self._target(),
                "stage_id": stage.id,
                "approval_authority_designation_id": self.designation.id,
            })

    def test_programme_change_requires_governed_approval_and_commercial_review(self):
        self.project.write({
            "hjig_pending_programme": "launchguard_design",
            "hjig_programme_change_reason": "Customer has contracted design services only.",
            "hjig_programme_commercial_review": "Reviewed quotation and revenue scope; no supplier commitment remains.",
            "hjig_programme_change_authority_id": self.designation.id,
        })
        self.project.action_request_hjig_programme_change()
        approval = self.project.hjig_programme_change_approval_id
        self.assertEqual(self.project.hjig_programme_change_status, "pending")
        self.assertTrue(approval.request_snapshot_hash)
        with self.assertRaises(ValidationError):
            self.project.hjig_programme_change_reason = "Changed during approval"
        approval.with_user(self.approver).action_approve()
        self.project.action_apply_hjig_programme_change()
        self.assertEqual(self.project.hjig_programme, "launchguard_design")
        self.assertEqual(self.project.hjig_programme_change_status, "approved")
        self.assertEqual(self.env["hjig.transition.log"].search_count([
            ("project_id", "=", self.project.id),
            ("decision", "=", "programme_route_changed"),
        ]), 1)
