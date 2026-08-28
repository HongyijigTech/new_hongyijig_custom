from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestExecutionQuality(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Execution Owner", "login": "execution.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Quality Approver", "login": "quality.approver@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id, cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id])],
        })
        cls.designation = cls.env["hjig.governance.designation"].create({
            "code": "QUALITY-AUTH", "name": "Quality Authority", "category": "quality",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Execution Quality Project", "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
        })
        cls.supplier = cls.env["res.partner"].create({"name": "China Toolmaker"})

    def _target(self):
        return "project.project,%s" % self.project.id

    def _evidence(self, label="evidence"):
        return self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": label, "source_party": "supplier",
            "source_url": "https://drive.google.com/%s" % label,
        })

    def test_weekly_report_requires_evidence_and_next_plan(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-001", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-01", "current_forecast_trial_date": "2026-09-05",
            "coordinator_id": self.owner.id,
        })
        report = self.env["hjig.tooling.report"].create({
            "execution_id": execution.id, "report_type": "weekly_progress", "reporting_period": "2026-W35",
            "planned_progress_percent": 50, "actual_progress_percent": 40,
            "approval_authority_designation_id": self.designation.id,
        })
        with self.assertRaises(ValidationError):
            report.action_submit_review()
        report.evidence_ids = self._evidence("weekly-photo")
        report.next_plan = "Complete core machining."
        report.with_user(self.owner).action_submit_review()
        report.approval_id.with_user(self.approver).action_approve()
        report.action_apply_decision()
        self.assertEqual(report.state, "approved")

    def test_tooling_requires_authoritative_or_external_mould_plan_reference(self):
        with self.assertRaises(ValidationError):
            self.env["hjig.tooling.execution"].create({
                "project_id": self.project.id, "supplier_id": self.supplier.id,
                "start_date": "2026-08-01", "baseline_trial_date": "2026-09-01",
                "current_forecast_trial_date": "2026-09-01", "coordinator_id": self.owner.id,
            })

    def test_dimensional_result_must_match_limits(self):
        inspection = self.env["hjig.inspection"].create({
            "project_id": self.project.id, "inspection_type": "dimensional",
            "supplier_id": self.supplier.id, "part_or_assembly_reference": "PART-001",
            "batch_reference": "T1-SAMPLE", "drawing_revision": "R03",
            "approval_authority_designation_id": self.designation.id,
        })
        with self.assertRaises(ValidationError):
            self.env["hjig.inspection.line"].create({
                "inspection_id": inspection.id, "characteristic_code": "D01",
                "check_type": "dimensional", "description": "Overall width",
                "lower_limit": 9.9, "upper_limit": 10.1, "measured_value": 10.3,
                "measurement_recorded": True, "unit": "mm", "instrument_reference": "CALIPER-CAL-001",
                "result": "pass",
            })

        valid_line = self.env["hjig.inspection.line"].create({
            "inspection_id": inspection.id, "characteristic_code": "D02",
            "check_type": "dimensional", "description": "Overall height",
            "lower_limit": 19.9, "upper_limit": 20.1, "measured_value": 20.0,
            "measurement_recorded": True, "unit": "mm", "instrument_reference": "HEIGHT-GAUGE-CAL-001",
            "result": "pass",
        })
        with self.assertRaises(ValidationError):
            valid_line.instrument_reference = False

    def test_inspection_requires_authoritative_or_external_part_reference(self):
        with self.assertRaises(ValidationError):
            self.env["hjig.inspection"].create({
                "project_id": self.project.id, "inspection_type": "part_visual",
                "supplier_id": self.supplier.id, "batch_reference": "T1-SAMPLE",
                "drawing_revision": "R03", "approval_authority_designation_id": self.designation.id,
            })

    def test_inspection_uses_shared_header_and_human_approval(self):
        inspection = self.env["hjig.inspection"].create({
            "project_id": self.project.id, "inspection_type": "part_visual",
            "supplier_id": self.supplier.id, "part_or_assembly_reference": "PART-001",
            "batch_reference": "T1-SAMPLE", "drawing_revision": "R03",
            "approval_authority_designation_id": self.designation.id, "disposition": "accept",
        })
        self.env["hjig.inspection.line"].create({
            "inspection_id": inspection.id, "characteristic_code": "V01",
            "check_type": "visual", "description": "Approved cosmetic surface",
            "critical": True, "result": "pass", "evidence_ids": [(6, 0, [self._evidence("visual-photo").id])],
        })
        inspection.with_user(self.owner).action_submit_review()
        inspection.approval_id.with_user(self.approver).action_approve()
        inspection.action_apply_decision()
        self.assertEqual(inspection.state, "approved")
        self.assertEqual(inspection.overall_result, "pass")
