from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


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

    def test_specified_requirement_needs_phase_allocation(self):
        sor = self._create_sor()
        self.env["hjig.sor.requirement"].create({
            "sor_id": sor.id, "requirement_id": "1.1", "category": "technical",
            "requirement_text": "Material shall match specification.",
            "declaration_state": "specified", "acceptance_criteria": "Material certificate accepted.",
        })
        with self.assertRaises(ValidationError):
            sor.action_submit_review()

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
