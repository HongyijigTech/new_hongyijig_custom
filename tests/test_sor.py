import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.new_hongyijig_custom.models.workflow_guard import workflow_context


@tagged("post_install", "-at_install")
class TestHongyiSor(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = cls.env["res.users"].create({
            "name": "SOR Owner", "login": "sor.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "SOR Approver", "login": "sor.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        cls.designation = cls.env["hjig.governance.designation"].create({
            "code": "SOR-APPROVER", "name": "SOR Approver", "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "SOR Test Project",
            "hjig_authorized_user_ids": [(6, 0, [cls.requester.id, cls.approver.id])],
        })

    def _create_sor(self, **overrides):
        values = {
            "project_id": self.project.id,
            "industry": "automotive",
            "intake_route": "hongyi_guided",
            "title": "Automotive SOR",
            "revision": "R00",
            "source_reference": "HONGYI-AUTO-SOR-v1",
            "owner_id": self.requester.id,
            "approval_authority_designation_id": self.designation.id,
            "effective_date": "2026-08-28",
        }
        values.update(overrides)
        return self.env["hjig.sor"].create(values)

    def _add_specified_requirement(self, sor):
        requirement = self.env["hjig.sor.requirement"].create({
            "sor_id": sor.id,
            "requirement_id": "7.7",
            "category": "quality",
            "requirement_text": "Trial part shall meet the approved visual standard.",
            "declaration_state": "specified",
            "source_reference": "Clause 7.7",
            "acceptance_criteria": "Approved visual inspection report with no critical defects.",
        })
        self.env["hjig.sor.requirement.verification"].create({
            "requirement_id": requirement.id,
            "phase": "trial",
            "check_required": True,
            "verification_method": "Visual inspection",
            "required_evidence": "Approved Part Visual Inspection Report",
            "responsible_designation_id": self.designation.id,
        })
        return requirement

    def test_route_a_requires_original_customer_document(self):
        with self.assertRaises(ValidationError):
            self._create_sor(
                intake_route="customer_sor", revision="R01",
                source_reference="Customer SOR R4", source_url=False,
            )

    def test_blank_is_not_a_requirement_state(self):
        sor = self._create_sor()
        with self.assertRaises(Exception):
            self.env["hjig.sor.requirement"].create({
                "sor_id": sor.id, "requirement_id": "1.1", "category": "technical",
                "requirement_text": "Material requirement", "declaration_state": False,
            })

    def test_automotive_guided_template_loads_sectioned_phase_mapped_requirements(self):
        sor = self._create_sor(revision="R10")
        sor.action_load_approved_template()
        self.assertEqual(sor.guided_template_code, "HONGYI-MASTER-AUTOMOTIVE-SOR")
        self.assertTrue(sor.guided_template_url.startswith("https://docs.google.com/document/"))
        self.assertGreaterEqual(len(sor.requirement_ids), 20)
        scope = sor.requirement_ids.filtered(lambda row: row.requirement_id == "AUTO-02.02")
        self.assertEqual(scope.section_code, "2")
        self.assertEqual(set(scope.verification_ids.mapped("phase")), {"design", "prototype", "trial"})
        self.assertEqual(scope.declaration_state, "pending")

    def test_medical_template_requires_order_punch_and_loads_only_selected_domain(self):
        sor = self._create_sor(
            revision="R11", industry="medical", title="Medical SOR",
            source_reference="SOR-MED-CE-HA-v2.1",
        )
        with self.assertRaises(ValidationError):
            sor.action_load_approved_template()
        sor.order_punch_confirmed = True
        sor.action_load_approved_template()
        domain = sor.requirement_ids.filtered(lambda row: row.requirement_id == "MCH-18.01")
        self.assertIn("Medical Devices", domain.requirement_text)
        self.assertNotIn("Home Appliances —", domain.requirement_text)
        self.assertGreaterEqual(len(sor.requirement_ids), 30)

    def test_option_c_requires_explicit_engineering_scope(self):
        sor = self._create_sor(
            revision="R12", industry="consumer_electronics", title="CE SOR",
            source_reference="SOR-MED-CE-HA-v2.1", order_punch_confirmed=True,
            engineering_responsibility="hjig_coordinated",
        )
        requirement = self._add_specified_requirement(sor)
        requirement.requirement_id = "CE-1"
        with self.assertRaises(ValidationError):
            sor.action_submit_review()

    def test_specified_requirement_needs_phase_allocation(self):
        sor = self._create_sor()
        self.env["hjig.sor.requirement"].create({
            "sor_id": sor.id, "requirement_id": "1.1", "category": "technical",
            "requirement_text": "Material shall match specification.",
            "declaration_state": "specified", "acceptance_criteria": "Material certificate accepted.",
        })
        with self.assertRaises(ValidationError):
            sor.action_submit_review()

    def test_verification_create_rejects_forged_controlled_result(self):
        sor = self._create_sor(revision="R06")
        requirement = self.env["hjig.sor.requirement"].create({
            "sor_id": sor.id, "requirement_id": "9.1", "category": "quality",
            "requirement_text": "Controlled verification result.",
            "declaration_state": "specified", "acceptance_criteria": "Accepted report.",
        })
        with self.assertRaises(ValidationError):
            self.env["hjig.sor.requirement.verification"].with_user(self.requester).create({
                "requirement_id": requirement.id, "phase": "trial", "check_required": True,
                "verification_method": "Visual inspection", "required_evidence": "Report",
                "responsible_designation_id": self.designation.id,
                "status": "pass", "verified_by_id": self.requester.id, "cycle": 7,
                "audit_history_json": '[{"cycle": 7, "result": "pass"}]',
            })

    def test_sor_freeze_uses_human_approval(self):
        sor = self._create_sor()
        self._add_specified_requirement(sor)
        sor.with_user(self.requester).action_submit_review()
        self.assertEqual(sor.state, "review")
        sor.baseline_id.approval_id.with_user(self.approver).action_approve()
        sor.action_apply_decision()
        self.assertEqual(sor.state, "frozen")
        self.assertEqual(sor.baseline_id.state, "approved")
        with self.assertRaises(ValidationError):
            sor.title = "Changed after freeze"

    def test_no_product_warranty_is_enforced(self):
        sor = self._create_sor()
        sor.write({"no_product_warranty": False})
        self.assertTrue(sor.no_product_warranty)

    def test_rejected_sor_reuses_baseline_for_resubmission(self):
        sor = self._create_sor(revision="R02")
        self._add_specified_requirement(sor)
        sor.with_user(self.requester).action_submit_review()
        baseline = sor.baseline_id
        baseline.approval_id.decision_reason = "Acceptance criteria need clarification."
        baseline.approval_id.with_user(self.approver).action_reject()
        sor.action_apply_decision()
        self.assertEqual(sor.state, "rejected")
        sor.with_user(self.requester).action_submit_review()
        self.assertEqual(sor.baseline_id, baseline)
        self.assertEqual(sor.state, "review")

    def test_phase_result_requires_independently_accepted_evidence(self):
        sor = self._create_sor(revision="R03")
        requirement = self._add_specified_requirement(sor)
        sor.with_user(self.requester).action_submit_review()
        sor.baseline_id.approval_id.with_user(self.approver).action_approve()
        sor.action_apply_decision()
        verification = requirement.verification_ids
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id,
            "target_ref": "hjig.sor.requirement,%s" % requirement.id,
            "evidence_type": "Trial inspection", "source_party": "hongyi",
            "source_url": "https://drive.google.com/trial-inspection",
        })
        verification.evidence_ids = evidence
        with self.assertRaises(ValidationError):
            verification.with_user(self.approver).action_pass()
        evidence.with_user(self.approver).action_accept()
        verification.with_user(self.approver).action_pass()
        self.assertEqual(verification.status, "pass")

    def test_failed_verification_evidence_is_locked_and_reopened_by_governance(self):
        sor = self._create_sor(revision="R04")
        requirement = self._add_specified_requirement(sor)
        sor.with_user(self.requester).action_submit_review()
        sor.baseline_id.approval_id.with_user(self.approver).action_approve()
        sor.action_apply_decision()
        verification = requirement.verification_ids
        first_evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id,
            "target_ref": "hjig.sor.requirement,%s" % requirement.id,
            "evidence_type": "Failed trial", "source_party": "hongyi",
            "source_url": "https://drive.google.com/failed-trial",
        })
        first_evidence.with_user(self.approver).action_accept()
        replacement = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id,
            "target_ref": "hjig.sor.requirement,%s" % requirement.id,
            "evidence_type": "Corrected trial", "source_party": "hongyi",
            "source_url": "https://drive.google.com/corrected-trial",
        })
        replacement.with_user(self.approver).action_accept()
        verification.evidence_ids = first_evidence
        verification.with_user(self.approver).action_fail()
        with self.assertRaises(ValidationError):
            verification.evidence_ids = [(6, 0, [replacement.id])]
        verification.reverification_reason = "Repeat trial after corrective action."
        verification.with_user(self.approver).action_reopen_failed()
        self.assertEqual(verification.cycle, 2)
        verification.evidence_ids = [(6, 0, [replacement.id])]
        verification.with_user(self.approver).action_pass()
        self.assertEqual(verification.status, "pass")
        history = json.loads(verification.audit_history_json)
        self.assertEqual([entry["cycle"] for entry in history], [1, 2])
        self.assertEqual(history[0]["result"], "fail")
        self.assertEqual(history[0]["evidence"][0]["id"], first_evidence.id)
        self.assertEqual(history[1]["result"], "pass")
        self.assertEqual(history[1]["evidence"][0]["id"], replacement.id)

    def test_reopen_requires_responsible_designation_and_current_frozen_sor(self):
        sor = self._create_sor(revision="R05")
        requirement = self._add_specified_requirement(sor)
        sor.with_user(self.requester).action_submit_review()
        sor.baseline_id.approval_id.with_user(self.approver).action_approve()
        sor.action_apply_decision()
        verification = requirement.verification_ids
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id,
            "target_ref": "hjig.sor.requirement,%s" % requirement.id,
            "evidence_type": "Failed controlled trial", "source_party": "hongyi",
            "source_url": "https://drive.google.com/failed-controlled-trial",
        })
        evidence.with_user(self.approver).action_accept()
        verification.evidence_ids = evidence
        verification.with_user(self.approver).action_fail()
        verification.reverification_reason = "Controlled retest required."

        unrelated_approver = self.env["res.users"].create({
            "name": "Unrelated SOR Approver",
            "login": "sor.unrelated.approver@test.invalid",
            "group_ids": [(6, 0, [
                self.env.ref("project.group_project_user").id,
                self.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        self.project.hjig_authorized_user_ids = [(4, unrelated_approver.id)]
        with self.assertRaises(UserError):
            verification.with_user(unrelated_approver).action_reopen_failed()

        sor.with_context(**workflow_context()).write({"state": "superseded"})
        with self.assertRaises(UserError):
            verification.with_user(self.approver).action_reopen_failed()
