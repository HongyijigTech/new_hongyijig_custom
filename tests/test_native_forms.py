import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNativeProjectForms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Native Form Owner",
            "login": "native.form.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Native Form Approver",
            "login": "native.form.approver@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_manager").id])],
        })
        cls.owner_designation = cls.env["hjig.governance.designation"].create({
            "code": "NATIVE-TEST-OWNER",
            "name": "Native Test Owner",
            "category": "engineering",
            "holder_ids": [(6, 0, [cls.owner.id])],
        })
        cls.approver_designation = cls.env["hjig.governance.designation"].create({
            "code": "NATIVE-TEST-APPROVER",
            "name": "Native Test Approver",
            "category": "project",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.stage = cls.env["hjig.launchguard.stage"].create({
            "code": "NATIVE-TEST-GATE",
            "name": "Native Test Gate",
            "sequence": 999,
            "stage_type": "technical_gate",
        })
        cls.project = cls.env["project.project"].create({
            "name": "Native Form Test Project",
            "hjig_project_record_type": "customer",
            "x_project_code": "HJ-NAT-2026-0001",
            "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
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
        cls.mould_artifact = cls._artifact("NATIVE-TEST-MPL", "Test Mould Plan")
        cls.visual_artifact = cls._artifact("NATIVE-TEST-VIR", "Test Visual Report")
        cls.assembly_artifact = cls._artifact("NATIVE-TEST-AIR", "Test Assembly Report")
        cls.dimensional_artifact = cls._artifact("NATIVE-TEST-DIR", "Test Dimensional Report")
        cls.mould_template = cls._template("NATIVE-TPL-MPL", "mould_plan", cls.mould_artifact)
        cls.visual_template = cls._template("NATIVE-TPL-VIR", "visual", cls.visual_artifact)
        cls.assembly_template = cls._template("NATIVE-TPL-AIR", "assembly", cls.assembly_artifact)
        cls.dimensional_template = cls._template("NATIVE-TPL-DIR", "dimensional", cls.dimensional_artifact)

    @classmethod
    def _artifact(cls, code, name):
        return cls.env["hjig.governance.artifact.master"].create({
            "code": code,
            "name": name,
            "artifact_type": "form",
            "applicable_stage_ids": [(6, 0, [cls.stage.id])],
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "default_register_type": "programme_internal",
            "default_document_class": "evidence",
            "revision": "1.0",
        })

    @classmethod
    def _template(cls, code, form_kind, artifact):
        return cls.env["hjig.native.form.template"].create({
            "code": code,
            "name": code,
            "form_kind": form_kind,
            "artifact_master_id": artifact.id,
            "stage_id": cls.stage.id,
            "revision": "TEST-1.0",
        })

    def _create_mould(self, complete=True):
        mould = self.env["x_mould"].create({
            "x_name": "Test Mould",
            "x_project_id": self.project.id,
            "x_mould_number": "TM-001",
            "x_template_id": self.mould_template.id,
            "x_owner_designation_id": self.owner_designation.id,
            "x_approver_designation_id": self.approver_designation.id,
            "x_effective_date": "2026-08-27",
        })
        part_values = {
            "x_mould_id": mould.id,
            "x_name": "Cover",
            "x_part_number": "P-001",
        }
        if complete:
            part_values.update({
                "x_part_category": "appearance",
                "x_surface_finish_type": "spi",
                "x_surface_grade_code": "SPI-B1",
                "x_part_material": "ABS",
                "x_customer_shrinkage": 0.5,
                "x_part_weight_grams": 125.0,
                "x_qps": 1,
                "x_visual_inspection_applicability": "required_critical",
                "x_dimensional_inspection_applicability": "required",
                "x_mould_base_steel_grade": "P20",
                "x_runner_type": "cold",
                "x_gate_type": "Edge Gate",
            })
        part = self.env["x_mould_part"].create(part_values)
        return mould, part

    def test_complete_mould_plan_can_be_approved_and_locks(self):
        mould, _part = self._create_mould()
        self.assertEqual(mould.x_completion_percent, 100.0)
        mould.with_user(self.owner).action_submit_review()
        mould.with_user(self.approver).action_approve()
        self.assertEqual(mould.x_workflow_state, "approved")
        self.assertEqual(mould.x_mould_planning_status, "final_locked")
        with self.assertRaises(ValidationError):
            mould.x_name = "Rewritten after approval"
        mould.x_planning_assumption = "IG-01 planning complete before architecture control."
        mould.action_advance_lifecycle()
        with self.assertRaises(ValidationError):
            self.env["x_mould_part"].create({
                "x_mould_id": mould.id,
                "x_name": "Late Part",
                "x_part_number": "P-LATE",
            })

    def test_approved_legacy_record_allows_lifecycle_work_but_not_identity_rewrite(self):
        mould, part = self._create_mould()
        mould.with_user(self.owner).action_submit_review()
        mould.with_user(self.approver).action_approve()
        mould.x_planning_assumption = "Lifecycle data remains editable at IG-01."
        part.x_colour = "Black"
        self.assertEqual(mould.x_planning_assumption, "Lifecycle data remains editable at IG-01.")
        self.assertEqual(part.x_colour, "Black")
        with self.assertRaises(ValidationError):
            mould.x_name = "Identity rewrite is still prohibited"

    def test_database_locked_staging_demo_allows_audited_same_user_mould_approval(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("new_hongyijig_custom.staging_self_approval_demo", "1")
        parameters.set_param(
            "new_hongyijig_custom.staging_self_approval_database", self.env.cr.dbname
        )
        assignment = self.env["hjig.project.designation.assignment"].search([
            ("project_id", "=", self.project.id),
            ("designation_id", "=", self.approver_designation.id),
        ])
        assignment.write({"holder_ids": [(6, 0, [self.owner.id])]})
        mould, _part = self._create_mould()
        mould.with_user(self.owner).action_submit_review()
        mould.with_user(self.owner).action_approve()
        self.assertEqual(mould.x_workflow_state, "approved")
        reasons = self.env["hjig.transition.log"].search([
            ("target_ref", "=", "%s,%s" % (mould._name, mould.id)),
        ]).mapped("reason")
        self.assertTrue(any("STAGING TRAINING OVERRIDE" in reason for reason in reasons))

    def test_project_code_locks_after_native_form_exists(self):
        self._create_mould()
        with self.assertRaises(ValidationError):
            self.project.x_project_code = "HJ-NAT-2026-0002"

    def test_incomplete_mould_plan_cannot_be_submitted(self):
        mould, _part = self._create_mould(complete=False)
        self.assertLess(mould.x_completion_percent, 100.0)
        with self.assertRaises(ValidationError):
            mould.with_user(self.owner).action_submit_review()

    def test_complete_mould_lifecycle_baseline_and_controlled_change(self):
        mould, _part = self._create_mould()
        mould.write({
            "x_planning_assumption": "Known part list and annual demand basis reviewed.",
            "x_cavitation_confirmed": True,
        })
        self.assertTrue(mould.x_stage_ready)
        mould.action_advance_lifecycle()
        self.assertEqual(mould.x_lifecycle_stage, "tg01")
        self.assertFalse(mould.x_stage_ready)
        mould.action_confirm_architecture_baseline()
        self.assertTrue(mould.x_stage_ready)
        with self.assertRaises(ValidationError):
            mould.x_mould_length_mm = 500
        mould.write({
            "x_change_reason": "Machine selection required a larger mould base.",
            "x_mould_length_mm": 500,
        })
        change = mould.x_change_log_ids.filtered(lambda item: item.field_name == "x_mould_length_mm")
        self.assertEqual(len(change), 1)
        self.assertEqual(change.reason, "Machine selection required a larger mould base.")

    def test_mould_machine_compatibility_and_image_evidence(self):
        mould, _part = self._create_mould()
        mould.write({
            "x_planning_assumption": "Machine and mould envelope confirmed for the test.",
            "x_cavitation_confirmed": True,
            "x_mould_length_mm": 400,
            "x_mould_width_mm": 350,
            "x_mould_height_mm": 300,
            "x_estimated_weight_kg": 800,
            "x_projected_area_cm2": 100,
            "x_planner_tonnage": 120,
            "x_machine_tonnage": 180,
            "x_machine_shot_capacity_g": 500,
            "x_tie_bar_x_mm": 600,
            "x_tie_bar_y_mm": 600,
            "x_platen_x_mm": 800,
            "x_platen_y_mm": 800,
            "x_machine_min_thickness_mm": 200,
            "x_machine_max_thickness_mm": 500,
            "x_machine_daylight_mm": 600,
            "x_handling_capacity_kg": 1200,
        })
        self.assertEqual(mould.x_machine_verdict, "pass")
        one_pixel_png = base64.b64encode(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        evidence = self.env["hjig.evidence.link"].create({
            "project_id": self.project.id,
            "target_ref": "x_mould,%s" % mould.id,
            "evidence_type": "Mould concept image",
            "source_party": "hongyi",
            "image_1920": one_pixel_png,
            "image_caption": "Controlled mould concept image",
            "image_stage": "ig01",
        })
        self.assertTrue(evidence.image_1920)
        self.assertEqual(evidence.verification_state, "unverified")

    def test_family_mould_uses_one_controlled_cavity_quantity_per_geometry(self):
        mould, first_part = self._create_mould()
        mould.x_mould_configuration = "family"
        second_part = self.env["x_mould_part"].create({
            "x_mould_id": mould.id,
            "x_name": "Button B",
            "x_part_number": "P-002",
            "x_part_category": "appearance",
            "x_surface_finish_type": "spi",
            "x_surface_grade_code": "SPI-B1",
            "x_part_material": "ABS",
            "x_colour": "Black",
            "x_customer_shrinkage": 0.5,
            "x_part_weight_grams": 20,
            "x_qps": 2,
            "x_visual_inspection_applicability": "required_critical",
            "x_dimensional_inspection_applicability": "required",
            "x_mould_base_steel_grade": "P20",
            "x_runner_type": "cold",
            "x_gate_type": "Edge Gate",
        })
        first_part.write({"x_colour": "Black"})
        geometry_a = self.env["hjig.mould.geometry"].create({
            "mould_id": mould.id, "code": "G1", "name": "Button A", "cavity_quantity": 1,
        })
        geometry_b = self.env["hjig.mould.geometry"].create({
            "mould_id": mould.id, "code": "G2", "name": "Button B", "cavity_quantity": 2,
        })
        first_part.x_geometry_id = geometry_a
        second_part.x_geometry_id = geometry_b
        mould.invalidate_recordset()
        self.assertEqual(mould.x_total_cavities, 3)
        self.assertEqual(geometry_a.krt_label, "1x1")
        self.assertEqual(geometry_b.krt_label, "1x2")

    def test_visual_report_auto_generates_approved_checkpoint_baseline(self):
        mould, part = self._create_mould()
        report = self.env["hjig.inspection.report"].create({
            "project_id": self.project.id,
            "template_id": self.visual_template.id,
            "mould_id": mould.id,
            "part_id": part.id,
            "revision": "R00",
            "effective_date": "2026-08-27",
        })
        self.assertEqual(len(report.point_ids), 41)
        self.assertEqual(report.point_ids[0].description, "Check for scratches, scuffs, and drag marks, even using magnification if necessary.")
        self.assertEqual(set(report.point_ids[0].trial_result_ids.mapped("trial_stage")), {"t0", "t1", "t2", "t3", "t4", "final"})
        self.assertEqual(report.overall_status, "pending")
        controlled_point = report.point_ids[0]
        with self.assertRaises(ValidationError):
            controlled_point.description = "Rewritten checkpoint"
        with self.assertRaises(UserError):
            controlled_point.unlink()
        controlled_point.not_required = True
        self.assertEqual(set(controlled_point.trial_result_ids.mapped("status")), {"na"})
        controlled_point.not_required = False
        self.assertEqual(set(controlled_point.trial_result_ids.mapped("status")), {"pending"})
        report.point_ids.trial_result_ids.write({"status": "pass"})
        self.assertEqual(report.overall_status, "pass")
        report.with_user(self.owner).action_submit_review()
        report.with_user(self.approver).action_approve()
        self.assertEqual(report.workflow_state, "approved")

    def test_assembly_report_auto_generates_baseline_and_enforces_phase_order(self):
        mould, part = self._create_mould()
        assembly = self.env["hjig.assembly"].create({
            "name": "Test Assembly",
            "code": "AP1",
            "project_id": self.project.id,
            "part_ids": [(6, 0, [part.id])],
            "inspection_applicability": "required",
        })
        report = self.env["hjig.inspection.report"].create({
            "project_id": self.project.id,
            "template_id": self.assembly_template.id,
            "mould_id": mould.id,
            "assembly_id": assembly.id,
            "revision": "R00",
        })
        self.assertEqual(len(report.point_ids), 33)
        self.assertEqual(len(report.point_ids.filtered(lambda item: item.phase == "during")), 14)
        self.assertEqual(len(report.point_ids.filtered(lambda item: item.phase == "after")), 19)
        after_t0 = report.point_ids.filtered(lambda item: item.sequence == 15).trial_result_ids.filtered(
            lambda item: item.trial_stage == "t0"
        )
        with self.assertRaises(ValidationError):
            after_t0.status = "pass"
        during_t0 = report.point_ids.filtered(lambda item: item.phase == "during").trial_result_ids.filtered(
            lambda item: item.trial_stage == "t0"
        )
        during_t0.write({"status": "pass"})
        after_t0.status = "pass"
        self.assertEqual(after_t0.status, "pass")

    def test_dimensional_limits_and_go_ng_are_automatic(self):
        mould, part = self._create_mould()
        report = self.env["hjig.inspection.report"].create({
            "project_id": self.project.id,
            "template_id": self.dimensional_template.id,
            "mould_id": mould.id,
            "part_id": part.id,
            "revision": "R00",
        })
        line = self.env["hjig.dimensional.line"].create({
            "report_id": report.id,
            "dimension_number": "D001",
            "drawing_dimension_mm": 10.0,
            "tolerance_minus_mm": 0.1,
            "tolerance_plus_mm": 0.2,
            "method_used": "digital_calliper",
        })
        self.assertAlmostEqual(line.min_dimension_mm, 9.9)
        self.assertAlmostEqual(line.max_dimension_mm, 10.2)
        go_result = self.env["hjig.dimensional.measurement"].create({
            "dimension_line_id": line.id,
            "trial_stage": "t0",
            "cavity_number": 1,
            "actual_dimension_mm": 10.1,
        })
        ng_result = self.env["hjig.dimensional.measurement"].create({
            "dimension_line_id": line.id,
            "trial_stage": "t0",
            "cavity_number": 2,
            "actual_dimension_mm": 10.3,
        })
        self.assertEqual(go_result.result, "go")
        self.assertEqual(ng_result.result, "ng")

    def test_engineering_dropdowns_copy_controlled_snapshots(self):
        material = self.env.ref("new_hongyijig_custom.plastic_material_001")
        finish = self.env.ref("new_hongyijig_custom.surface_finish_spi_004")
        steel = self.env.ref("new_hongyijig_custom.tool_steel_001")
        gate = self.env.ref("new_hongyijig_custom.gate_type_001")
        mould, part = self._create_mould(complete=False)
        part.write({
            "x_part_category": "appearance",
            "x_surface_finish_id": finish.id,
            "x_material_master_id": material.id,
            "x_customer_shrinkage": 0.5,
            "x_part_weight_grams": 125.0,
            "x_qps": 1,
            "x_visual_inspection_applicability": "required_noncritical",
            "x_dimensional_inspection_applicability": "required",
            "x_mould_base_steel_id": steel.id,
            "x_runner_type": "cold",
            "x_gate_type_id": gate.id,
        })
        self.assertEqual(part.x_part_material, material.name)
        self.assertEqual(part.x_standard_shrinkage, material.shrinkage_range)
        self.assertEqual(part.x_surface_grade_code, finish.code)
        self.assertEqual(part.x_gate_type, gate.name)
        self.assertEqual(part.x_completion_percent, 100.0)
        with self.assertRaises(ValidationError):
            material.name = "Rewritten approved baseline"

    def test_dimensional_method_dropdown_keeps_legacy_snapshot(self):
        mould, part = self._create_mould()
        report = self.env["hjig.inspection.report"].create({
            "project_id": self.project.id,
            "template_id": self.dimensional_template.id,
            "mould_id": mould.id,
            "part_id": part.id,
            "revision": "R01",
        })
        method = self.env.ref("new_hongyijig_custom.inspection_method_001")
        line = self.env["hjig.dimensional.line"].create({
            "report_id": report.id,
            "dimension_number": "D002",
            "drawing_dimension_mm": 20.0,
            "tolerance_minus_mm": 0.1,
            "tolerance_plus_mm": 0.1,
            "method_master_id": method.id,
        })
        self.assertEqual(line.method_used, "digital_calliper")

    def test_governed_cavitation_follows_mould_configuration(self):
        single, _part = self._create_mould()
        self.assertEqual(single.x_cavitation, "1")
        with self.assertRaises(ValidationError):
            single.x_cavitation = "1*2"

        family = self.env["x_mould"].create({
            "x_name": "Family Mould",
            "x_project_id": self.project.id,
            "x_mould_number": "TM-FAMILY",
            "x_mould_configuration": "family",
            "x_template_id": self.mould_template.id,
        })
        part_1 = self.env["x_mould_part"].create({
            "x_mould_id": family.id,
            "x_name": "First",
            "x_part_number": "F-001",
            "x_sequence": 10,
            "x_cavity_plan": 1,
        })
        part_2 = self.env["x_mould_part"].create({
            "x_mould_id": family.id,
            "x_name": "Second",
            "x_part_number": "F-002",
            "x_sequence": 20,
            "x_cavity_plan": 4,
        })
        self.assertEqual(family.x_cavitation, "1+4")
        part_2.x_cavity_plan = 2
        self.assertEqual(family.x_cavitation, "1+2")
        with self.assertRaises(ValidationError):
            family.x_cavitation = "9+9"
        part_1.unlink()
        self.assertEqual(family.x_cavitation, "2")

        multi = self.env["x_mould"].create({
            "x_name": "Multi Mould",
            "x_project_id": self.project.id,
            "x_mould_number": "TM-MULTI",
            "x_mould_configuration": "multi",
            "x_cavitation": "1*2",
            "x_template_id": self.mould_template.id,
        })
        self.assertEqual(multi.x_cavitation, "1*2")
        multi.x_cavitation = "1*4"
        self.assertEqual(multi.x_cavitation, "1*4")

    def test_inspection_applicability_blocks_not_required_sessions(self):
        mould, part = self._create_mould()
        part.x_visual_inspection_applicability = "not_required"
        with self.assertRaises(ValidationError):
            self.env["hjig.inspection.report"].create({
                "project_id": self.project.id,
                "template_id": self.visual_template.id,
                "mould_id": mould.id,
                "part_id": part.id,
                "revision": "R-NR",
            })
        part.x_dimensional_inspection_applicability = "not_required"
        with self.assertRaises(ValidationError):
            self.env["hjig.inspection.report"].create({
                "project_id": self.project.id,
                "template_id": self.dimensional_template.id,
                "mould_id": mould.id,
                "part_id": part.id,
                "revision": "R-NR",
            })

    def test_critical_dimensions_block_submission_but_noncritical_ng_does_not(self):
        mould, part = self._create_mould()
        report = self.env["hjig.inspection.report"].create({
            "project_id": self.project.id,
            "template_id": self.dimensional_template.id,
            "mould_id": mould.id,
            "part_id": part.id,
            "revision": "R-CRIT",
        })
        method = self.env.ref("new_hongyijig_custom.inspection_method_001")
        critical = self.env["hjig.dimensional.line"].create({
            "report_id": report.id,
            "dimension_number": "CRIT-1",
            "critical_dimension": True,
            "drawing_dimension_mm": 10.0,
            "tolerance_minus_mm": 0.1,
            "tolerance_plus_mm": 0.1,
            "method_master_id": method.id,
        })
        noncritical = self.env["hjig.dimensional.line"].create({
            "report_id": report.id,
            "dimension_number": "NONCRIT-1",
            "drawing_dimension_mm": 20.0,
            "tolerance_minus_mm": 0.1,
            "tolerance_plus_mm": 0.1,
            "method_master_id": method.id,
        })
        critical_result = self.env["hjig.dimensional.measurement"].create({
            "dimension_line_id": critical.id,
            "trial_stage": "t0",
            "cavity_number": 1,
            "actual_dimension_mm": 10.5,
        })
        self.env["hjig.dimensional.measurement"].create({
            "dimension_line_id": noncritical.id,
            "trial_stage": "t0",
            "cavity_number": 1,
            "actual_dimension_mm": 20.5,
        })
        with self.assertRaises(ValidationError):
            report.with_user(self.owner).action_submit_review()
        critical_result.actual_dimension_mm = 10.0
        report.with_user(self.owner).action_submit_review()
        self.assertEqual(report.workflow_state, "review")
