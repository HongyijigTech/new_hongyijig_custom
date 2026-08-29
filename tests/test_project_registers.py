import base64

from odoo.exceptions import AccessError, UserError, ValidationError
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
        cls.outsider = cls.env["res.users"].create({
            "name": "Register Outsider", "login": "register.outsider@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
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
        for designation, holder in (
            (cls.owner_designation, cls.owner),
            (cls.approver_designation, cls.approver),
        ):
            cls.env["hjig.project.designation.assignment"].create({
                "project_id": cls.project.id,
                "designation_id": designation.id,
                "holder_ids": [(6, 0, [holder.id])],
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
            "x_visual_inspection_applicability": "required_critical",
            "x_dimensional_inspection_applicability": "required",
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

    def test_final_mould_plan_rejects_fabricated_or_incomplete_snapshot(self):
        mould, part = self._approved_mould()
        plan = self.env["hjig.final.mould.plan"].create({
            "project_id": self.project.id, "revision": "R01",
            "source_mould_ids": [(6, 0, [mould.id])],
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "effective_date": "2026-08-27",
        })
        forged = plan._snapshot_values(mould, part)
        forged.update({"plan_id": plan.id, "part_name": "Fabricated value"})
        with self.assertRaises(ValidationError):
            self.env["hjig.final.mould.plan.line"].create(forged)
        plan.action_generate_lines()
        plan.line_ids.unlink()
        with self.assertRaises(ValidationError):
            plan.with_user(self.owner).action_submit_review()

    def test_final_mould_plan_context_cannot_bypass_authority(self):
        mould, _part = self._approved_mould()
        plan = self.env["hjig.final.mould.plan"].create({
            "project_id": self.project.id, "revision": "R02",
            "source_mould_ids": [(6, 0, [mould.id])],
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "effective_date": "2026-08-27",
        })
        plan.action_generate_lines()
        with self.assertRaises(UserError):
            plan.with_user(self.outsider).with_context(allow_final_plan_workflow=True).write({
                "workflow_state": "review", "submitted_by_id": self.outsider.id,
            })

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

    def test_risk_intermediate_workflow_is_designation_controlled(self):
        risk = self.env["hjig.project.risk"].create({
            "project_id": self.project.id, "description": "Controlled workflow risk",
            "category": "technical", "probability": "3", "impact": "3",
            "mitigation_plan": "Execute countermeasure",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "target_date": "2026-09-10", "next_review_date": "2026-08-30",
        })
        with self.assertRaises(UserError):
            risk.with_user(self.outsider).action_start_mitigation()
        risk.with_user(self.owner).action_start_mitigation()
        risk.with_user(self.approver).action_accept()
        self.assertEqual(risk.status, "accepted")

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
        with self.assertRaises(ValidationError):
            issue.with_user(self.approver).action_close()

    def test_issue_rejects_unrelated_attachment_and_invalid_link(self):
        issue = self.env["hjig.project.issue"].create({
            "project_id": self.project.id, "description": "Unverified closure",
            "category": "quality", "priority": "critical",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "next_review_date": "2026-08-30", "target_closure_date": "2026-09-02",
            "root_cause": "Recorded", "closure_notes": "Claimed closed",
        })
        unrelated = self.env["ir.attachment"].create({
            "name": "unrelated.txt", "datas": base64.b64encode(b"unrelated"),
            "res_model": "project.project", "res_id": self.project.id,
        })
        issue.write({"closure_attachment_ids": [(6, 0, [unrelated.id])]})
        with self.assertRaises(ValidationError):
            issue.with_user(self.approver).action_close()
        issue.write({"closure_attachment_ids": [(5, 0, 0)], "closure_evidence_url": "not-a-valid-url"})
        with self.assertRaises(ValidationError):
            issue.with_user(self.approver).action_close()

    def test_issue_intermediate_workflow_is_designation_controlled(self):
        issue = self.env["hjig.project.issue"].create({
            "project_id": self.project.id, "description": "Controlled workflow issue",
            "category": "schedule", "priority": "high",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "next_review_date": "2026-08-30", "target_closure_date": "2026-09-02",
        })
        with self.assertRaises(UserError):
            issue.with_user(self.outsider).action_start_work()
        issue.with_user(self.owner).action_start_work()
        issue.with_user(self.owner).action_block()
        issue.with_user(self.owner).action_resume()
        self.assertEqual(issue.status, "in_progress")

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
            "remarks": "No supplier or customer approval is required for this controlled test.",
        })
        ecn.with_user(self.owner).action_submit_review()
        with self.assertRaises(ValidationError):
            ecn.with_user(self.approver).action_approve()
        ecn.write({"customer_approval_status": "not_required"})
        ecn.with_user(self.approver).action_approve()
        with self.assertRaises(ValidationError):
            ecn.with_user(self.owner).write({"description": "Changed after approval"})
        ecn.with_user(self.owner).write({"implementation_date": "2026-08-28"})
        ecn.with_user(self.owner).action_mark_implemented()
        ecn.with_user(self.approver).action_close()
        self.assertEqual(ecn.status, "closed")

    def test_ecn_context_cannot_bypass_submission_authority(self):
        mould, _part = self._approved_mould()
        ecn = self.env["hjig.project.ecn"].create({
            "project_id": self.project.id, "description": "Unauthorized ECN attempt",
            "component_name": "Housing", "change_reason": "Test",
            "impacted_mould_ids": [(6, 0, [mould.id])],
            "raised_by_designation_id": self.owner_designation.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        with self.assertRaises(UserError):
            ecn.with_user(self.outsider).with_context(allow_ecn_workflow=True).write({
                "status": "review", "submitted_by_id": self.outsider.id,
            })

    def test_private_project_registers_follow_project_visibility(self):
        private_project = self.env["project.project"].create({
            "name": "Private Register Project", "privacy_visibility": "invited_users",
            "hjig_project_record_type": "customer", "x_project_code": "HJ-LGC-2026-9001",
        })
        risk = self.env["hjig.project.risk"].create({
            "project_id": private_project.id, "description": "Private commercial risk",
            "category": "commercial", "probability": "3", "impact": "4",
            "mitigation_plan": "Restricted review", "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "target_date": "2026-09-10", "next_review_date": "2026-08-30",
        })
        self.assertFalse(self.env["hjig.project.risk"].with_user(self.owner).search([("id", "=", risk.id)]))
        with self.assertRaises(AccessError):
            risk.with_user(self.owner).read(["description"])
        self.assertEqual(self.env["hjig.project.risk"].with_user(self.approver).search([("id", "=", risk.id)]), risk)
