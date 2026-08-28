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
            "hjig_authorized_user_ids": [(6, 0, [cls.requester.id, cls.approver.id])],
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
