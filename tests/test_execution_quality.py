from types import SimpleNamespace

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.execution_quality import _reference_project


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

    def _evidence(self, label="evidence", accepted=True):
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id, "target_ref": self._target(),
            "evidence_type": label, "source_party": "supplier",
            "source_url": "https://drive.google.com/%s" % label,
        })
        if accepted:
            evidence.with_user(self.approver).action_accept()
        return evidence

    def test_reference_project_supports_direct_and_sourcebridge_paths(self):
        direct = SimpleNamespace(project_id=self.project, x_project_id=False)
        sourcebridge = SimpleNamespace(
            project_id=False,
            x_project_id=False,
            engagement_id=SimpleNamespace(project_id=self.project),
        )
        unresolved = SimpleNamespace(project_id=False, x_project_id=False, engagement_id=False)
        self.assertEqual(_reference_project(direct), self.project)
        self.assertEqual(_reference_project(sourcebridge), self.project)
        self.assertFalse(_reference_project(unresolved))

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
        with self.assertRaises(ValidationError):
            report.with_user(self.owner).next_plan = "Altered after submission."
        with self.assertRaises(ValidationError):
            report.with_user(self.owner).evidence_ids = [(5, 0, 0)]
        report.approval_id.with_user(self.approver).action_approve()
        report.action_apply_decision()
        self.assertEqual(report.state, "approved")

    def test_tooling_report_rejects_unaccepted_evidence(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-UNVERIFIED", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-01", "current_forecast_trial_date": "2026-09-05",
            "coordinator_id": self.owner.id,
        })
        report = self.env["hjig.tooling.report"].create({
            "execution_id": execution.id, "report_type": "weekly_progress",
            "reporting_period": "2026-W36", "planned_progress_percent": 60,
            "actual_progress_percent": 55, "next_plan": "Finish validation.",
            "approval_authority_designation_id": self.designation.id,
            "evidence_ids": [(6, 0, [self._evidence("unverified-weekly", accepted=False).id])],
        })
        with self.assertRaises(ValidationError):
            report.with_user(self.owner).action_submit_review()

    def test_tooling_requires_authoritative_or_external_mould_plan_reference(self):
        with self.assertRaises(ValidationError):
            self.env["hjig.tooling.execution"].create({
                "project_id": self.project.id, "supplier_id": self.supplier.id,
                "start_date": "2026-08-01", "baseline_trial_date": "2026-09-01",
                "current_forecast_trial_date": "2026-09-01", "coordinator_id": self.owner.id,
            })

    def test_weekly_report_links_structured_manufacturing_plan(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-LINKED", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-15", "current_forecast_trial_date": "2026-09-15",
            "coordinator_id": self.owner.id,
        })
        plan_line = self.env["hjig.tooling.plan.line"].create({
            "execution_id": execution.id, "code": "MFG-010", "operation": "Core rough machining",
            "owner_id": self.owner.id, "planned_start": "2026-08-03", "planned_end": "2026-08-10",
        })
        report = self.env["hjig.tooling.report"].create({
            "execution_id": execution.id, "report_type": "weekly_progress", "reporting_period": "2026-W32",
            "planned_progress_percent": 20, "actual_progress_percent": 15,
            "next_plan": "Finish rough machining.", "approval_authority_designation_id": self.designation.id,
            "evidence_ids": [(6, 0, [self._evidence("linked-plan-weekly").id])],
        })
        with self.assertRaises(ValidationError):
            report.action_submit_review()
        report.plan_line_ids = plan_line
        report.action_submit_review()
        self.assertEqual(report.state, "review")

    def test_completed_manufacturing_plan_line_requires_actual_completion(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-COMPLETE", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-15", "current_forecast_trial_date": "2026-09-15",
            "coordinator_id": self.owner.id,
        })
        with self.assertRaises(ValidationError):
            self.env["hjig.tooling.plan.line"].create({
                "execution_id": execution.id, "code": "MFG-020", "operation": "Heat treatment",
                "owner_id": self.owner.id, "planned_start": "2026-08-11", "planned_end": "2026-08-14",
                "state": "complete", "progress_percent": 100,
            })

    def test_manufacturing_plan_line_has_employee_readable_display_name(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-DISPLAY", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-15", "current_forecast_trial_date": "2026-09-15",
            "coordinator_id": self.owner.id,
        })
        line = self.env["hjig.tooling.plan.line"].create({
            "execution_id": execution.id, "code": "MFG-030", "operation": "Polishing",
            "owner_id": self.owner.id, "planned_start": "2026-08-15", "planned_end": "2026-08-17",
        })
        self.assertEqual(line.display_name, "MFG-030 — Polishing")

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

    def test_inspection_rejects_unaccepted_line_evidence(self):
        inspection = self.env["hjig.inspection"].create({
            "project_id": self.project.id, "inspection_type": "part_visual",
            "supplier_id": self.supplier.id, "part_or_assembly_reference": "PART-002",
            "batch_reference": "T1-UNVERIFIED", "drawing_revision": "R03",
            "approval_authority_designation_id": self.designation.id, "disposition": "accept",
        })
        self.env["hjig.inspection.line"].create({
            "inspection_id": inspection.id, "characteristic_code": "V02",
            "check_type": "visual", "description": "Cosmetic surface",
            "critical": True, "result": "pass",
            "evidence_ids": [(6, 0, [self._evidence("unverified-visual", accepted=False).id])],
        })
        with self.assertRaises(ValidationError):
            inspection.with_user(self.owner).action_submit_review()

    def test_closed_supplier_action_is_immutable(self):
        execution = self.env["hjig.tooling.execution"].create({
            "project_id": self.project.id, "supplier_id": self.supplier.id,
            "mould_plan_reference": "MP-2026-ACTION", "start_date": "2026-08-01",
            "baseline_trial_date": "2026-09-01", "current_forecast_trial_date": "2026-09-05",
            "coordinator_id": self.owner.id,
        })
        evidence = self._evidence("action-closure", accepted=False)
        action = self.env["hjig.tooling.action"].create({
            "execution_id": execution.id, "title": "Correct ejector alignment",
            "owner_id": self.owner.id, "due_date": "2026-08-31",
            "closure_evidence_ids": [(6, 0, [evidence.id])],
        })
        action.with_user(self.owner).action_start()
        action.with_user(self.owner).action_request_verification()
        with self.assertRaises(ValidationError):
            action.with_user(self.approver).action_close()
        evidence.with_user(self.approver).action_accept()
        action.with_user(self.approver).action_close()
        with self.assertRaises(ValidationError):
            action.title = "Changed after closure"
        with self.assertRaises(ValidationError):
            action.closure_evidence_ids = [(5, 0, 0)]
