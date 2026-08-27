import base64

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectRegisters(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Register Owner", "login": "register.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Register Approver", "login": "register.approver@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_manager").id])],
        })
        cls.owner_designation = cls.env["hjig.governance.designation"].create({
            "code": "REGISTER-TEST-OWNER", "name": "Register Test Owner", "category": "engineering",
            "holder_ids": [(6, 0, [cls.owner.id])],
        })
        cls.approver_designation = cls.env["hjig.governance.designation"].create({
            "code": "REGISTER-TEST-APPROVER", "name": "Register Test Approver", "category": "project",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Register Test Project", "hjig_project_record_type": "customer",
            "x_project_code": "HJ-REG-2026-0001",
        })

    def _approved_mould(self):
        mould = self.env["x_mould"].create({
            "x_name": "Register Test Mould", "x_project_id": self.project.id,
            "x_mould_number": "REG-M-001",
            "x_template_id": self.env.ref("new_hongyijig_custom.native_template_mould_plan").id,
            "x_owner_designation_id": self.owner_designation.id,
            "x_approver_designation_id": self.approver_designation.id,
            "x_effective_date": "2026-08-27",
        })
        part = self.env["x_mould_part"].create({
            "x_mould_id": mould.id, "x_name": "Housing", "x_part_number": "REG-P-001",
            "x_part_category": "appearance", "x_surface_finish_type": "spi",
            "x_surface_grade_code": "A2", "x_part_material": "ABS",
            "x_customer_shrinkage": 0.5, "x_part_weight_grams": 120.0, "x_qps": 1,
            "x_mould_configuration": "single", "x_cavitation": "1*1",
            "x_mould_base_steel_grade": "P20", "x_runner_type": "cold", "x_gate_type": "Edge Gate",
        })
        mould.with_user(self.owner).action_submit_review()
        mould.with_user(self.approver).action_approve()
        return mould, part

    def test_final_mould_plan_generation_and_lock(self):
        mould, part = self._approved_mould()
        plan = self.env["hjig.final.mould.plan"].create({
            "project_id": self.project.id, "revision": "R00",
            "source_mould_ids": [(6, 0, [mould.id])],
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "effective_date": "2026-08-27",
        })
        plan.action_generate_lines()
        self.assertEqual(plan.line_count, 1)
        self.assertEqual(plan.line_ids.source_part_id, part)
        plan.with_user(self.owner).action_submit_review()
        plan.with_user(self.approver).action_approve()
        with self.assertRaises(ValidationError):
            plan.revision = "R01"

    def test_risk_score_and_resolution_lock(self):
        risk = self.env["hjig.project.risk"].create({
            "project_id": self.project.id, "description": "Trial date may slip",
            "category": "schedule", "probability": "4", "impact": "5",
            "mitigation_plan": "Daily recovery review",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "target_date": "2026-09-10", "next_review_date": "2026-08-30",
            "resolution_notes": "Recovery plan completed",
        })
        self.assertEqual(risk.risk_score, 20)
        self.assertTrue(risk.escalation_required)
        risk.with_user(self.approver).action_resolve()
        with self.assertRaises(ValidationError):
            risk.description = "Rewritten"

    def test_issue_needs_evidence_to_close(self):
        issue = self.env["hjig.project.issue"].create({
            "project_id": self.project.id, "description": "Part flash observed",
            "category": "quality", "priority": "high",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "next_review_date": "2026-08-30", "target_closure_date": "2026-09-02",
        })
        with self.assertRaises(ValidationError):
            issue.with_user(self.approver).action_close()
        attachment = self.env["ir.attachment"].create({
            "name": "closure-evidence.txt", "datas": base64.b64encode(b"verified closure evidence"),
            "res_model": "hjig.project.issue", "res_id": issue.id,
        })
        issue.write({"root_cause": "Shut-off mismatch", "closure_notes": "Corrected and rechecked",
                     "closure_attachment_ids": [(6, 0, [attachment.id])]})
        issue.with_user(self.approver).action_close()
        self.assertEqual(issue.status, "closed")

    def test_ecn_approval_and_implementation_flow(self):
        _mould, part = self._approved_mould()
        ecn = self.env["hjig.project.ecn"].create({
            "project_id": self.project.id, "description": "Increase rib thickness",
            "component_name": "Housing", "change_reason": "Strength improvement",
            "impacted_part_ids": [(6, 0, [part.id])],
            "raised_by_designation_id": self.owner_designation.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "supplier_approval_status": "not_required", "customer_approval_status": "pending",
        })
        ecn.with_user(self.owner).action_submit_review()
        with self.assertRaises(ValidationError):
            ecn.with_user(self.approver).action_approve()
        ecn.write({"customer_approval_status": "not_required"})
        ecn.with_user(self.approver).action_approve()
        ecn.implementation_date = "2026-08-28"
        ecn.with_user(self.owner).action_mark_implemented()
        ecn.with_user(self.approver).action_close()
        self.assertEqual(ecn.status, "closed")
