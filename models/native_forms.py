# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import (
    record_staging_demo_transition,
    staging_self_approval_demo_enabled,
)


TRIAL_STAGES = [
    ("t0", "T0"),
    ("t1", "T1"),
    ("t2", "T2"),
    ("t3", "T3"),
    ("t4", "T4"),
    ("final", "Final Trial"),
]


class HjigNativeFormTemplate(models.Model):
    _name = "hjig.native.form.template"
    _description = "Native Project Form Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, code"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10, required=True)
    form_kind = fields.Selection(
        [
            ("mould_plan", "Mould Planning"),
            ("visual", "Part Visual Inspection"),
            ("assembly", "Assembly Inspection"),
            ("dimensional", "Dimensional Inspection"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    artifact_master_id = fields.Many2one(
        "hjig.governance.artifact.master",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    revision = fields.Char(required=True, default="1.0", tracking=True)
    source_tab_name = fields.Char(readonly=True)
    description = fields.Text()
    active = fields.Boolean(default=True, tracking=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Native form template code must be unique.",
    )
    _kind_revision_unique = models.Constraint(
        "UNIQUE(form_kind, revision)",
        "Only one native template may exist for the same form kind and revision.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        governed = {"code", "name", "form_kind", "artifact_master_id", "stage_id", "revision"}
        used = self.env["x_mould"].search_count([("x_template_id", "in", self.ids)])
        used += self.env["hjig.inspection.report"].search_count([("template_id", "in", self.ids)])
        if governed.intersection(vals) and used:
            raise ValidationError(
                _("A template already used by a project form cannot be rewritten. Archive it and create a new revision.")
            )
        return super().write(vals)


class HjigInspectionCheckpointMaster(models.Model):
    _name = "hjig.inspection.checkpoint.master"
    _description = "Controlled Inspection Checkpoint Master"
    _order = "form_kind, sequence, id"

    form_kind = fields.Selection(
        [("visual", "Part Visual Inspection"), ("assembly", "Assembly Inspection")],
        required=True,
        index=True,
    )
    sequence = fields.Integer(required=True)
    phase = fields.Selection(
        [("during", "During Assembly"), ("after", "After Assembly Complete")],
        help="Used only by Assembly Inspection. Visual checkpoints have no phase gate.",
    )
    category = fields.Char(required=True)
    checkpoint_text = fields.Text(required=True)
    default_not_required = fields.Boolean()
    source_specification = fields.Char(required=True, readonly=True)
    source_url = fields.Char(required=True, readonly=True)
    active = fields.Boolean(default=True)

    _kind_sequence_unique = models.Constraint(
        "UNIQUE(form_kind, sequence)",
        "Checkpoint sequence must be unique within each inspection form.",
    )

    @api.constrains("form_kind", "phase", "sequence")
    def _check_checkpoint_master(self):
        for checkpoint in self:
            if checkpoint.form_kind == "visual" and checkpoint.phase:
                raise ValidationError(_("Visual checkpoints cannot carry an Assembly phase."))
            if checkpoint.form_kind == "assembly" and not checkpoint.phase:
                raise ValidationError(_("Assembly checkpoints require a controlled phase."))
            if checkpoint.sequence <= 0:
                raise ValidationError(_("Checkpoint sequence must be positive."))

    @api.model_create_multi
    def create(self, vals_list):
        source_urls = {
            "visual": "https://docs.google.com/document/d/1rfKLmNQ11Gkh1rEQBZTlI6WjNHj6F0CGxOZbzndFl_0/edit",
            "assembly": "https://docs.google.com/document/d/1YcZ2X6jb1YtGfvEVspfEg5dvw-gtogMzypb77ywHU64/edit",
        }
        for vals in vals_list:
            vals.setdefault("source_url", source_urls.get(vals.get("form_kind")))
        return super().create(vals_list)

    def write(self, vals):
        governed = {"form_kind", "sequence", "phase", "category", "checkpoint_text", "source_specification", "source_url"}
        used = self.env["hjig.inspection.point"].search_count([("checkpoint_master_id", "in", self.ids)])
        if governed.intersection(vals) and used:
            raise ValidationError(
                _("A checkpoint already used by an inspection report cannot be rewritten. Archive it and create a revised baseline.")
            )
        return super().write(vals)

    def unlink(self):
        if self.env["hjig.inspection.point"].search_count([("checkpoint_master_id", "in", self.ids)]):
            raise UserError(_("A checkpoint used by an inspection report cannot be deleted. Archive it instead."))
        return super().unlink()

class HjigMould(models.Model):
    """Code-owned continuation of the existing production PN Mould model."""

    _name = "x_mould"
    _description = "Project Mould Planning Form"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "x_name"
    _order = "x_project_id, x_mould_number, id"

    x_name = fields.Char(string="Name", required=True, tracking=True)
    x_active = fields.Boolean(string="Active", default=True, tracking=True)
    x_project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    x_mould_number = fields.Char(
        string="Mould Number / Identifier",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    x_mould_description = fields.Char(string="Mould Name / Description", tracking=True)
    x_mould_configuration = fields.Selection(
        [("single", "Single Cavity"), ("multi", "Multi Cavity"), ("family", "Family Mould")],
        string="Mould Configuration",
        required=True,
        default="single",
        tracking=True,
    )
    x_cavitation = fields.Char(string="Cavitation", default="1", tracking=True)
    x_mould_planning_status = fields.Selection(
        [("tentative", "Tentative"), ("final_locked", "Final - Locked")],
        string="Mould Planning Status",
        required=True,
        default="tentative",
        tracking=True,
    )
    x_template_id = fields.Many2one(
        "hjig.native.form.template",
        string="Form Template",
        domain="[('form_kind', '=', 'mould_plan')]",
        ondelete="restrict",
        tracking=True,
    )
    x_plan_revision = fields.Char(string="Plan Revision", default="R00", required=True, tracking=True)
    x_workflow_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
            ("superseded", "Superseded"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    x_owner_designation_id = fields.Many2one(
        "hjig.governance.designation",
        string="Owner Designation",
        ondelete="restrict",
        tracking=True,
    )
    x_approver_designation_id = fields.Many2one(
        "hjig.governance.designation",
        string="Approver Designation",
        ondelete="restrict",
        tracking=True,
    )
    x_submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    x_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    x_effective_date = fields.Date(tracking=True)
    x_part_ids = fields.One2many("x_mould_part", "x_mould_id", string="Component / Part Planning")
    x_part_count = fields.Integer(compute="_compute_part_summary")
    x_completion_percent = fields.Float(compute="_compute_part_summary", store=True)
    x_missing_fields = fields.Text(compute="_compute_part_summary", store=True)

    _project_mould_revision_unique = models.Constraint(
        "UNIQUE(x_project_id, x_mould_number, x_plan_revision)",
        "The same mould number and plan revision already exists in this project.",
    )

    @api.depends(
        "x_mould_configuration", "x_cavitation",
        "x_part_ids", "x_part_ids.x_completion_percent", "x_part_ids.x_missing_fields",
    )
    def _compute_part_summary(self):
        for mould in self:
            mould.x_part_count = len(mould.x_part_ids)
            header_missing = []
            if not mould.x_mould_configuration:
                header_missing.append(_("Mould Configuration"))
            if not mould.x_cavitation:
                header_missing.append(_("Cavitation"))
            if not mould.x_part_ids:
                header_missing.append(_("At least one component / part is required"))
            part_completion = (
                sum(mould.x_part_ids.mapped("x_completion_percent")) / len(mould.x_part_ids)
                if mould.x_part_ids else 0.0
            )
            header_completion = 100.0 * (
                2 - len([item for item in header_missing if item != _("At least one component / part is required")])
            ) / 2
            mould.x_completion_percent = (header_completion + part_completion) / 2 if mould.x_part_ids else 0.0
            incomplete = mould.x_part_ids.filtered(lambda part: part.x_missing_fields)
            part_missing = [
                "%s: %s" % (part.x_part_number or part.x_name, part.x_missing_fields)
                for part in incomplete
            ]
            mould.x_missing_fields = "\n".join(header_missing + part_missing)

    def _sync_governed_cavitation(self):
        for mould in self:
            expected = False
            if mould.x_mould_configuration == "single":
                expected = "1"
            elif mould.x_mould_configuration == "family":
                plans = mould.x_part_ids.sorted(lambda part: (part.x_sequence, part.id)).mapped("x_cavity_plan")
                expected = "+".join(str(plan) for plan in plans if plan > 0) or False
            if mould.x_mould_configuration in ("single", "family") and mould.x_cavitation != expected:
                mould.with_context(allow_governed_cavitation=True).write({"x_cavitation": expected})

    @api.onchange("x_mould_configuration", "x_part_ids", "x_part_ids.x_cavity_plan", "x_part_ids.x_sequence")
    def _onchange_governed_cavitation(self):
        for mould in self:
            if mould.x_mould_configuration == "single":
                mould.x_cavitation = "1"
            elif mould.x_mould_configuration == "family":
                plans = mould.x_part_ids.sorted(lambda part: (part.x_sequence, part.id)).mapped("x_cavity_plan")
                mould.x_cavitation = "+".join(str(plan) for plan in plans if plan > 0) or False
            elif mould._origin.x_mould_configuration in ("single", "family"):
                mould.x_cavitation = False

    @api.model_create_multi
    def create(self, vals_list):
        template = self.env.ref("new_hongyijig_custom.native_template_mould_plan", raise_if_not_found=False)
        for vals in vals_list:
            vals["x_workflow_state"] = "draft"
            vals["x_mould_planning_status"] = "tentative"
            vals.setdefault("x_mould_configuration", "single")
            if vals["x_mould_configuration"] == "single":
                vals["x_cavitation"] = "1"
            elif vals["x_mould_configuration"] == "family":
                vals["x_cavitation"] = False
            vals.setdefault("x_template_id", template.id if template else False)
            if template:
                vals.setdefault("x_owner_designation_id", template.artifact_master_id.owner_designation_id.id)
                vals.setdefault("x_approver_designation_id", template.artifact_master_id.approver_designation_id.id)
            if not vals.get("x_mould_number"):
                vals["x_mould_number"] = self.env["ir.sequence"].next_by_code("hjig.mould") or _("New")
        moulds = super().create(vals_list)
        moulds._sync_governed_cavitation()
        requirement_id = self.env.context.get("hjig_programme_artifact_requirement_id")
        if requirement_id and len(moulds) == 1:
            requirement = self.env["hjig.programme.run.artifact"].browse(requirement_id).exists()
            if requirement and requirement.artifact_code == "FRM-005":
                requirement.mould_plan_id = moulds.id
        for mould in moulds:
            self.env["hjig.programme.run.artifact"]._link_native_record_across_gates(
                mould, "FRM-005", "mould_plan_id"
            )
        return moulds

    def write(self, vals):
        locked_fields = set(self._fields) - {"message_follower_ids", "message_ids", "activity_ids"}
        if locked_fields.intersection(vals) and self.filtered(lambda item: item.x_workflow_state in ("approved", "superseded")):
            if not self.env.context.get("allow_native_form_workflow"):
                raise ValidationError(_("Approved or superseded mould plans are read-only."))
        if "x_workflow_state" in vals and not self.env.context.get("allow_native_form_workflow"):
            if any(item.x_workflow_state != vals["x_workflow_state"] for item in self):
                raise ValidationError(_("Use the controlled workflow buttons to change status."))
        if "x_cavitation" in vals and not self.env.context.get("allow_governed_cavitation"):
            for mould in self:
                configuration = vals.get("x_mould_configuration", mould.x_mould_configuration)
                if configuration != "multi" and vals["x_cavitation"] != mould.x_cavitation:
                    raise ValidationError(_("Cavitation is automatic for Single Cavity and Family Mould configurations."))
        result = super().write(vals)
        if "x_mould_configuration" in vals:
            self._sync_governed_cavitation()
        return result

    def unlink(self):
        if any(item.x_workflow_state != "draft" for item in self):
            raise UserError(_("Only Draft mould plans may be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for mould in self:
            if mould.x_workflow_state != "draft":
                raise UserError(_("Only Draft mould plans can be submitted."))
            if not mould.x_template_id or not mould.x_owner_designation_id or not mould.x_approver_designation_id:
                raise ValidationError(_("Template and designation authority must be configured before submission."))
            if not mould.x_owner_designation_id._user_holds_for_project(
                self.env.user, mould.x_project_id
            ):
                raise UserError(_("Only a current holder of the Owner Designation may submit this mould plan."))
            if mould.x_missing_fields:
                raise ValidationError(_("Complete the mould plan before submission:\n%s") % mould.x_missing_fields)
            mould.with_context(allow_native_form_workflow=True).write({
                "x_workflow_state": "review",
                "x_submitted_by_id": self.env.user.id,
            })

    def action_approve(self):
        for mould in self:
            if mould.x_workflow_state != "review":
                raise UserError(_("Only mould plans Under Review can be approved."))
            if not mould.x_approver_designation_id._user_holds_for_project(
                self.env.user, mould.x_project_id
            ):
                raise UserError(_("Only a current holder of the Approver Designation may approve this mould plan."))
            same_user_demo = (
                mould.x_submitted_by_id == self.env.user
                and staging_self_approval_demo_enabled(self.env)
            )
            if mould.x_submitted_by_id == self.env.user and not same_user_demo:
                raise ValidationError(_("The same user cannot submit and approve the mould plan."))
            if not mould.x_effective_date:
                raise ValidationError(_("Effective Date is required before approval."))
            mould.with_context(allow_native_form_workflow=True).write({
                "x_workflow_state": "approved",
                "x_mould_planning_status": "final_locked",
                "x_approved_by_id": self.env.user.id,
            })
            if same_user_demo:
                record_staging_demo_transition(
                    mould, "review", "approved", "staging_demo_approved"
                )


class HjigMouldPart(models.Model):
    """Code-owned continuation of the existing production PN Component/Part model."""

    _name = "x_mould_part"
    _description = "Mould Planning Component / Part"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "x_name"
    _order = "x_mould_id, x_sequence, id"

    x_name = fields.Char(string="Name", required=True, tracking=True)
    x_active = fields.Boolean(string="Active", default=True)
    x_mould_id = fields.Many2one("x_mould", string="Mould", required=True, ondelete="restrict", index=True)
    x_project_id = fields.Many2one(related="x_mould_id.x_project_id", store=True, index=True)
    x_sequence = fields.Integer(string="Part Sequence", default=10, required=True, tracking=True)
    x_part_number = fields.Char(string="Part Number / Identifier", required=True, tracking=True)
    x_material_reference = fields.Char(string="Material Reference")
    x_source_version = fields.Char(string="Source / Version Traceability")
    x_part_picture = fields.Image(string="Part Picture", attachment=True)
    x_part_category = fields.Selection(
        [
            ("appearance", "Appearance Part"),
            ("structural", "Structural Part"),
            ("assembly", "Assembly Part"),
            ("water_contact", "Water Contact Part"),
            ("safety", "Safety Part"),
            ("other", "Other"),
        ],
        tracking=True,
    )
    x_surface_finish_type = fields.Selection(
        [("spi", "SPI Grade"), ("vdi", "VDI Code"), ("special", "Special Texture")],
        tracking=True,
    )
    x_surface_finish_id = fields.Many2one(
        "hjig.surface.finish.master",
        string="Surface Finish / Texture",
        domain="[('finish_system', '=', x_surface_finish_type), ('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_surface_grade_code = fields.Char(string="Surface Grade / Code", tracking=True)
    x_surface_details = fields.Text(string="Surface Finish Details", readonly=True)
    x_material_master_id = fields.Many2one(
        "hjig.plastic.material.master",
        string="Part Material",
        domain="[('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_part_material = fields.Char(string="Part Material", tracking=True)
    x_standard_shrinkage = fields.Char(string="Standard Shrinkage Range", readonly=True)
    x_customer_shrinkage = fields.Float(string="Customer Shrinkage %", tracking=True)
    x_part_weight_grams = fields.Float(string="Part Weight (grams)", tracking=True)
    x_qps = fields.Integer(string="QPS", tracking=True)
    x_mould_configuration = fields.Selection(
        [("single", "Single Cavity"), ("multi", "Multi Cavity"), ("family", "Family Mould")],
        tracking=True,
    )
    x_cavitation = fields.Char(string="Cavitation", tracking=True)
    x_cavity_plan = fields.Integer(string="Cavity Plan for Family Mould", tracking=True)
    x_visual_inspection_applicability = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("required_noncritical", "Required - Non-Critical"),
            ("required_critical", "Required - Critical"),
        ],
        string="Visual Inspection Applicability",
        tracking=True,
    )
    x_dimensional_inspection_applicability = fields.Selection(
        [("not_required", "Not Required"), ("required", "Required")],
        string="Dimensional Inspection Applicability",
        tracking=True,
    )
    x_mould_base_steel_grade = fields.Selection(
        [(value, value) for value in ("P20", "718H", "NAK80", "S136", "H13", "8407", "Customer Specified")],
        tracking=True,
    )
    x_mould_base_steel_id = fields.Many2one(
        "hjig.tool.steel.master",
        string="Mould Base Steel",
        domain="[('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_core_steel_id = fields.Many2one(
        "hjig.tool.steel.master",
        string="Core Steel",
        domain="[('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_core_steel_brand = fields.Char(tracking=True)
    x_core_steel_grade = fields.Char(tracking=True)
    x_core_steel_usage = fields.Text()
    x_cavity_steel_brand = fields.Char(tracking=True)
    x_cavity_steel_grade = fields.Char(tracking=True)
    x_cavity_steel_usage = fields.Text()
    x_cavity_steel_id = fields.Many2one(
        "hjig.tool.steel.master",
        string="Cavity Steel",
        domain="[('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_runner_type = fields.Selection([("hot", "Hot Runner"), ("cold", "Cold Runner"), ("hybrid", "Hybrid")], tracking=True)
    x_gate_type_id = fields.Many2one(
        "hjig.gate.type.master",
        string="Gate Type",
        domain="[('runner_type', '=', x_runner_type), ('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
    )
    x_gate_type = fields.Char(tracking=True)
    x_gate_specifications = fields.Text(readonly=True)
    x_assumption_status = fields.Selection(
        [("assumed", "Assumed"), ("validated", "Validated"), ("tbd", "TBD / Risk")],
        default="assumed",
        required=True,
        tracking=True,
    )
    x_completion_percent = fields.Float(compute="_compute_completeness", store=True)
    x_missing_fields = fields.Char(compute="_compute_completeness", store=True)

    _mould_part_number_unique = models.Constraint(
        "UNIQUE(x_mould_id, x_part_number)",
        "Part Number must be unique within a mould plan.",
    )

    @api.model
    def _reference_snapshot_values(self, vals):
        vals = dict(vals)
        if vals.get("x_surface_finish_id"):
            finish = self.env["hjig.surface.finish.master"].browse(vals["x_surface_finish_id"]).exists()
            if finish:
                vals.update({
                    "x_surface_finish_type": finish.finish_system,
                    "x_surface_grade_code": finish.code,
                    "x_surface_details": "\n".join(filter(None, [
                        finish.name, finish.method, finish.appearance, finish.roughness_or_depth,
                        finish.recommended_draft and _("Recommended draft: %s") % finish.recommended_draft,
                        finish.tooling_notes,
                    ])),
                })
        if vals.get("x_material_master_id"):
            material = self.env["hjig.plastic.material.master"].browse(vals["x_material_master_id"]).exists()
            if material:
                vals.update({
                    "x_part_material": material.name,
                    "x_material_reference": material.code,
                    "x_standard_shrinkage": material.shrinkage_range,
                })
        for relational, brand_field, grade_field, usage_field in (
            ("x_core_steel_id", "x_core_steel_brand", "x_core_steel_grade", "x_core_steel_usage"),
            ("x_cavity_steel_id", "x_cavity_steel_brand", "x_cavity_steel_grade", "x_cavity_steel_usage"),
        ):
            if vals.get(relational):
                steel = self.env["hjig.tool.steel.master"].browse(vals[relational]).exists()
                if steel:
                    vals.update({brand_field: steel.manufacturer, grade_field: steel.grade, usage_field: steel.applications})
        if vals.get("x_mould_base_steel_id"):
            vals["x_mould_base_steel_grade"] = "Customer Specified"
        if vals.get("x_gate_type_id"):
            gate = self.env["hjig.gate.type.master"].browse(vals["x_gate_type_id"]).exists()
            if gate:
                vals.update({
                    "x_runner_type": gate.runner_type,
                    "x_gate_type": gate.name,
                    "x_gate_specifications": "\n".join(filter(None, [
                        gate.common_name, gate.typical_applications,
                        gate.suitable_materials and _("Suitable materials: %s") % gate.suitable_materials,
                        gate.advantages and _("Advantages: %s") % gate.advantages,
                        gate.risks and _("Risks: %s") % gate.risks,
                    ])),
                })
        return vals

    @api.depends(
        "x_name", "x_part_number", "x_part_category", "x_surface_finish_type",
        "x_surface_finish_id", "x_surface_grade_code", "x_material_master_id", "x_part_material", "x_customer_shrinkage",
        "x_part_weight_grams", "x_qps", "x_mould_id.x_mould_configuration", "x_cavity_plan",
        "x_visual_inspection_applicability", "x_dimensional_inspection_applicability",
        "x_mould_base_steel_id", "x_mould_base_steel_grade", "x_runner_type", "x_gate_type_id", "x_gate_type",
    )
    def _compute_completeness(self):
        required = [
            ("x_name", _("Part Name")), ("x_part_number", _("Part Number")),
            ("x_part_category", _("Part Category")), ("x_surface_finish_type", _("Surface Finish Type")),
            (("x_surface_finish_id", "x_surface_grade_code"), _("Surface Grade / Code")),
            (("x_material_master_id", "x_part_material"), _("Part Material")),
            ("x_customer_shrinkage", _("Customer Shrinkage %")), ("x_part_weight_grams", _("Part Weight")),
            ("x_qps", _("QPS")),
            ("x_visual_inspection_applicability", _("Visual Inspection Applicability")),
            ("x_dimensional_inspection_applicability", _("Dimensional Inspection Applicability")),
            (("x_mould_base_steel_id", "x_mould_base_steel_grade"), _("Mould Base Steel")),
            ("x_runner_type", _("Runner Type")), (("x_gate_type_id", "x_gate_type"), _("Gate Type")),
        ]
        for part in self:
            part_required = list(required)
            if part.x_mould_id.x_mould_configuration == "family":
                part_required.append(("x_cavity_plan", _("Cavity Plan for Family Mould")))
            missing = []
            for field_names, label in part_required:
                field_names = (field_names,) if isinstance(field_names, str) else field_names
                if not any(part[field_name] for field_name in field_names):
                    missing.append(label)
            part.x_missing_fields = ", ".join(missing)
            part.x_completion_percent = 100.0 * (len(part_required) - len(missing)) / len(part_required)

    @api.onchange("x_surface_finish_type")
    def _onchange_surface_finish_type(self):
        if self.x_surface_finish_id.finish_system != self.x_surface_finish_type:
            self.x_surface_finish_id = False
            self.x_surface_grade_code = False
            self.x_surface_details = False

    @api.onchange("x_surface_finish_id")
    def _onchange_surface_finish_id(self):
        finish = self.x_surface_finish_id
        if finish:
            self.x_surface_finish_type = finish.finish_system
            self.x_surface_grade_code = finish.code
            self.x_surface_details = "\n".join(filter(None, [
                finish.name,
                finish.method,
                finish.appearance,
                finish.roughness_or_depth,
                finish.recommended_draft and _("Recommended draft: %s") % finish.recommended_draft,
                finish.tooling_notes,
            ]))

    @api.onchange("x_material_master_id")
    def _onchange_material_master_id(self):
        material = self.x_material_master_id
        if material:
            self.x_part_material = material.name
            self.x_material_reference = material.code
            self.x_standard_shrinkage = material.shrinkage_range

    @api.onchange("x_mould_base_steel_id")
    def _onchange_mould_base_steel_id(self):
        if self.x_mould_base_steel_id:
            self.x_mould_base_steel_grade = "Customer Specified"

    @api.onchange("x_core_steel_id")
    def _onchange_core_steel_id(self):
        steel = self.x_core_steel_id
        if steel:
            self.x_core_steel_brand = steel.manufacturer
            self.x_core_steel_grade = steel.grade
            self.x_core_steel_usage = steel.applications

    @api.onchange("x_cavity_steel_id")
    def _onchange_cavity_steel_id(self):
        steel = self.x_cavity_steel_id
        if steel:
            self.x_cavity_steel_brand = steel.manufacturer
            self.x_cavity_steel_grade = steel.grade
            self.x_cavity_steel_usage = steel.applications

    @api.onchange("x_runner_type")
    def _onchange_runner_type(self):
        if self.x_gate_type_id.runner_type != self.x_runner_type:
            self.x_gate_type_id = False
            self.x_gate_type = False
            self.x_gate_specifications = False

    @api.onchange("x_gate_type_id")
    def _onchange_gate_type_id(self):
        gate = self.x_gate_type_id
        if gate:
            self.x_runner_type = gate.runner_type
            self.x_gate_type = gate.name
            self.x_gate_specifications = "\n".join(filter(None, [
                gate.common_name,
                gate.typical_applications,
                gate.suitable_materials and _("Suitable materials: %s") % gate.suitable_materials,
                gate.advantages and _("Advantages: %s") % gate.advantages,
                gate.risks and _("Risks: %s") % gate.risks,
            ]))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._reference_snapshot_values(vals) for vals in vals_list]
        for vals in vals_list:
            mould = self.env["x_mould"].browse(vals.get("x_mould_id")).exists()
            if mould and mould.x_workflow_state != "draft":
                raise ValidationError(_("Components may only be added while the mould plan is Draft."))
        parts = super().create(vals_list)
        parts.mapped("x_mould_id")._sync_governed_cavitation()
        return parts

    @api.constrains("x_customer_shrinkage", "x_part_weight_grams", "x_qps", "x_cavity_plan")
    def _check_positive_values(self):
        for part in self:
            if part.x_customer_shrinkage < 0 or part.x_customer_shrinkage > 100:
                raise ValidationError(_("Customer Shrinkage must be between 0 and 100 percent."))
            if part.x_part_weight_grams < 0 or part.x_qps < 0:
                raise ValidationError(_("Part Weight and QPS cannot be negative."))
            if part.x_cavity_plan < 0:
                raise ValidationError(_("Cavity Plan cannot be negative."))

    def write(self, vals):
        if any(part.x_mould_id.x_workflow_state in ("approved", "superseded") for part in self):
            raise ValidationError(_("Components of an approved or superseded mould plan are read-only."))
        moulds = self.mapped("x_mould_id")
        result = super().write(self._reference_snapshot_values(vals))
        if {"x_cavity_plan", "x_sequence", "x_mould_id"}.intersection(vals):
            (moulds | self.mapped("x_mould_id"))._sync_governed_cavitation()
        return result

    def unlink(self):
        if any(part.x_mould_id.x_workflow_state != "draft" for part in self):
            raise UserError(_("Components may only be deleted while the mould plan is Draft."))
        moulds = self.mapped("x_mould_id")
        result = super().unlink()
        moulds._sync_governed_cavitation()
        return result


class HjigAssembly(models.Model):
    _name = "hjig.assembly"
    _description = "Project Assembly"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, code, id"

    name = fields.Char(string="Assembly Name", required=True, tracking=True)
    code = fields.Char(string="Assembly Code", required=True, tracking=True, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    part_ids = fields.Many2many("x_mould_part", string="Parts Involved", tracking=True)
    inspection_applicability = fields.Selection(
        [("not_required", "Not Required"), ("required", "Required")],
        string="Assembly Inspection Applicability",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)

    _project_assembly_code_unique = models.Constraint(
        "UNIQUE(project_id, code)",
        "Assembly Code must be unique within the project.",
    )

    @api.constrains("project_id", "part_ids")
    def _check_part_projects(self):
        for assembly in self:
            if assembly.part_ids.filtered(lambda part: part.x_project_id != assembly.project_id):
                raise ValidationError(_("Every Part in an Assembly must belong to the same project."))

    def write(self, vals):
        governed = {"name", "code", "project_id", "part_ids", "inspection_applicability"}
        if governed.intersection(vals) and self.env["hjig.inspection.report"].search_count([("assembly_id", "in", self.ids)]):
            raise ValidationError(_("An Assembly already used by an inspection report cannot be rewritten."))
        return super().write(vals)

    def unlink(self):
        if self.env["hjig.inspection.report"].search_count([("assembly_id", "in", self.ids)]):
            raise UserError(_("An Assembly used by an inspection report cannot be deleted. Archive it instead."))
        return super().unlink()


class HjigInspectionReport(models.Model):
    _name = "hjig.inspection.report"
    _description = "Native Project Inspection Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "report_number"
    _order = "project_id, report_number desc"

    report_number = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    project_code = fields.Char(related="project_id.x_project_code", store=True, readonly=True)
    template_id = fields.Many2one("hjig.native.form.template", required=True, ondelete="restrict", tracking=True)
    report_type = fields.Selection(
        [("visual", "Part Visual Inspection"), ("assembly", "Assembly Inspection"), ("dimensional", "Dimensional Inspection")],
        required=True,
        index=True,
        tracking=True,
    )
    mould_id = fields.Many2one("x_mould", ondelete="restrict", tracking=True)
    part_id = fields.Many2one("x_mould_part", ondelete="restrict", tracking=True)
    assembly_id = fields.Many2one("hjig.assembly", ondelete="restrict", tracking=True)
    assembly_name = fields.Char(tracking=True)
    report_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    revision = fields.Char(default="R00", required=True, tracking=True)
    report_status = fields.Selection(
        [("in_progress", "In Progress"), ("complete_submitted", "Complete & Submitted")],
        default="in_progress",
        required=True,
        tracking=True,
    )
    workflow_state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"), ("superseded", "Superseded")],
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    effective_date = fields.Date(tracking=True)
    point_ids = fields.One2many("hjig.inspection.point", "report_id", string="Inspection Points")
    dimension_line_ids = fields.One2many("hjig.dimensional.line", "report_id", string="Dimensions")
    notes = fields.Text()
    overall_status = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail")],
        compute="_compute_overall_status",
        store=True,
    )

    _report_number_unique = models.Constraint("UNIQUE(report_number)", "Inspection Report Number must be unique.")
    _project_report_revision_unique = models.Constraint(
        "UNIQUE(project_id, report_type, mould_id, part_id, revision)",
        "The same inspection report revision already exists for this project, mould and part.",
    )
    _project_assembly_report_revision_unique = models.Constraint(
        "UNIQUE(project_id, report_type, assembly_id, revision)",
        "The same Assembly Inspection report revision already exists for this project and assembly.",
    )

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id and self.template_id.form_kind != "mould_plan":
            self.report_type = self.template_id.form_kind
            self.owner_designation_id = self.template_id.artifact_master_id.owner_designation_id
            self.approver_designation_id = self.template_id.artifact_master_id.approver_designation_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            template = self.env["hjig.native.form.template"].browse(vals.get("template_id")).exists()
            if not template:
                raise ValidationError(_("A native Form Template is required."))
            if template.form_kind == "mould_plan":
                raise ValidationError(_("Mould Planning templates cannot create an Inspection Report."))
            vals["report_type"] = template.form_kind
            part = self.env["x_mould_part"].browse(vals.get("part_id")).exists()
            assembly = self.env["hjig.assembly"].browse(vals.get("assembly_id")).exists()
            if template.form_kind == "visual":
                if not part or not part.x_visual_inspection_applicability:
                    raise ValidationError(_("Set Visual Inspection Applicability on the selected Part first."))
                if part.x_visual_inspection_applicability == "not_required":
                    raise ValidationError(_("A Visual Inspection report cannot be created for a Not Required Part."))
            if template.form_kind == "dimensional":
                if not part or not part.x_dimensional_inspection_applicability:
                    raise ValidationError(_("Set Dimensional Inspection Applicability on the selected Part first."))
                if part.x_dimensional_inspection_applicability == "not_required":
                    raise ValidationError(_("A Dimensional Inspection report cannot be created for a Not Required Part."))
            if template.form_kind == "assembly":
                if not assembly:
                    raise ValidationError(_("Select a governed Assembly before creating an Assembly Inspection report."))
                if assembly.inspection_applicability == "not_required":
                    raise ValidationError(_("An Assembly Inspection report cannot be created for a Not Required Assembly."))
                vals["assembly_name"] = assembly.code
            vals.setdefault("owner_designation_id", template.artifact_master_id.owner_designation_id.id)
            vals.setdefault("approver_designation_id", template.artifact_master_id.approver_designation_id.id)
            if vals.get("report_number", _("New")) == _("New"):
                vals["report_number"] = self.env["ir.sequence"].next_by_code("hjig.inspection.report") or _("New")
        reports = super().create(vals_list)
        checkpoint_model = self.env["hjig.inspection.checkpoint.master"]
        point_model = self.env["hjig.inspection.point"]
        for report in reports.filtered(lambda item: item.report_type in ("visual", "assembly")):
            checkpoints = checkpoint_model.search([
                ("form_kind", "=", report.report_type),
                ("active", "=", True),
            ], order="sequence, id")
            expected = 41 if report.report_type == "visual" else 33
            if len(checkpoints) != expected:
                raise ValidationError(
                    _("The controlled %s baseline must contain exactly %s active checkpoints; found %s.")
                    % (report.template_id.name, expected, len(checkpoints))
                )
            point_model.with_context(hjig_checkpoint_generation=True).create([{
                "report_id": report.id,
                "checkpoint_master_id": checkpoint.id,
                "sequence": checkpoint.sequence,
                "description": checkpoint.checkpoint_text,
                "not_required": checkpoint.default_not_required,
                "involved_part_ids": [(6, 0, report.assembly_id.part_ids.ids)]
                if report.report_type == "assembly" else False,
            } for checkpoint in checkpoints])
        return reports

    @api.depends(
        "point_ids.not_required", "point_ids.trial_result_ids.status",
        "dimension_line_ids.critical_dimension", "dimension_line_ids.measurement_ids.measurement_taken",
        "dimension_line_ids.measurement_ids.result",
    )
    def _compute_overall_status(self):
        for report in self:
            if report.report_type == "dimensional":
                measurements = report.dimension_line_ids.measurement_ids
                if (
                    not report.dimension_line_ids
                    or any(not line.measurement_ids for line in report.dimension_line_ids)
                    or measurements.filtered(lambda measurement: not measurement.measurement_taken)
                ):
                    report.overall_status = "pending"
                elif measurements.filtered(lambda measurement: measurement.result == "ng"):
                    report.overall_status = "fail"
                else:
                    report.overall_status = "pass"
                continue
            results = report.point_ids.filtered(lambda point: not point.not_required).trial_result_ids
            if not results or results.filtered(lambda result: result.status == "pending"):
                report.overall_status = "pending"
            elif results.filtered(lambda result: result.status == "fail"):
                report.overall_status = "fail"
            else:
                report.overall_status = "pass"

    @api.constrains("template_id", "report_type", "mould_id", "part_id", "assembly_id", "assembly_name")
    def _check_report_structure(self):
        for report in self:
            if report.template_id.form_kind != report.report_type:
                raise ValidationError(_("Report Type must follow the selected native Form Template."))
            if report.mould_id and report.mould_id.x_project_id != report.project_id:
                raise ValidationError(_("The selected mould belongs to a different project."))
            if report.part_id and report.part_id.x_project_id != report.project_id:
                raise ValidationError(_("The selected part belongs to a different project."))
            if report.assembly_id and report.assembly_id.project_id != report.project_id:
                raise ValidationError(_("The selected Assembly belongs to a different project."))
            if report.report_type in ("visual", "dimensional") and not report.part_id:
                raise ValidationError(_("Part Visual and Dimensional reports require a Part."))
            if report.report_type == "visual" and report.part_id.x_visual_inspection_applicability not in (
                "required_noncritical", "required_critical"
            ):
                raise ValidationError(_("Visual Inspection is not applicable to the selected Part."))
            if report.report_type == "dimensional" and report.part_id.x_dimensional_inspection_applicability != "required":
                raise ValidationError(_("Dimensional Inspection is not applicable to the selected Part."))
            if report.report_type == "assembly" and not (report.assembly_id or report.assembly_name):
                raise ValidationError(_("Assembly Inspection reports require an Assembly."))
            if report.assembly_id and report.assembly_id.inspection_applicability != "required":
                raise ValidationError(_("Assembly Inspection is not applicable to the selected Assembly."))

    def write(self, vals):
        if vals.get("template_id"):
            template = self.env["hjig.native.form.template"].browse(vals["template_id"]).exists()
            if not template or template.form_kind == "mould_plan":
                raise ValidationError(_("Select a valid native Inspection Form Template."))
            vals.update({
                "report_type": template.form_kind,
                "owner_designation_id": template.artifact_master_id.owner_designation_id.id,
                "approver_designation_id": template.artifact_master_id.approver_designation_id.id,
            })
        controlled = set(vals) - {"message_follower_ids", "message_ids", "activity_ids"}
        if controlled and self.filtered(lambda item: item.workflow_state in ("approved", "superseded")):
            if not self.env.context.get("allow_native_form_workflow"):
                raise ValidationError(_("Approved or superseded inspection reports are read-only."))
        if "workflow_state" in vals and not self.env.context.get("allow_native_form_workflow"):
            if any(item.workflow_state != vals["workflow_state"] for item in self):
                raise ValidationError(_("Use the controlled workflow buttons to change status."))
        return super().write(vals)

    def unlink(self):
        if any(item.workflow_state != "draft" for item in self):
            raise UserError(_("Only Draft inspection reports may be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for report in self:
            if report.workflow_state != "draft":
                raise UserError(_("Only Draft reports can be submitted."))
            if not report.owner_designation_id._user_holds_for_project(
                self.env.user, report.project_id
            ):
                raise UserError(_("Only a current holder of the Owner Designation may submit this report."))
            if report.report_type == "dimensional" and not report.dimension_line_ids:
                raise ValidationError(_("Add at least one dimensional inspection line."))
            if report.report_type != "dimensional" and not report.point_ids:
                raise ValidationError(_("Add at least one inspection point."))
            if report.report_type != "dimensional":
                results = report.point_ids.filtered(lambda point: not point.not_required).trial_result_ids
                if results.filtered(lambda result: result.status == "pending"):
                    raise ValidationError(_("Every applicable checkpoint must be evaluated before submission."))
                critical_visual = (
                    report.report_type == "visual"
                    and report.part_id.x_visual_inspection_applicability == "required_critical"
                )
                if (report.report_type == "assembly" or critical_visual) and results.filtered(
                    lambda result: result.status == "fail"
                ):
                    raise ValidationError(_("Every gate-blocking checkpoint must be Pass before submission."))
            if report.report_type == "dimensional" and any(
                not line.measurement_ids for line in report.dimension_line_ids
            ):
                raise ValidationError(_("Every dimensional line requires at least one cavity measurement."))
            if report.report_type == "dimensional" and report.dimension_line_ids.measurement_ids.filtered(
                lambda measurement: not measurement.measurement_taken
            ):
                raise ValidationError(_("Every recorded dimensional measurement must be completed before submission."))
            if report.report_type == "dimensional" and report.dimension_line_ids.filtered(
                lambda line: line.critical_dimension
                and line.measurement_ids.filtered(lambda measurement: measurement.result != "go")
            ):
                raise ValidationError(_("Every Critical Dimension must be GO before submission."))
            report.with_context(allow_native_form_workflow=True).write({
                "workflow_state": "review",
                "report_status": "complete_submitted",
                "submitted_by_id": self.env.user.id,
            })

    def action_approve(self):
        for report in self:
            if report.workflow_state != "review":
                raise UserError(_("Only reports Under Review can be approved."))
            if not report.approver_designation_id._user_holds_for_project(
                self.env.user, report.project_id
            ):
                raise UserError(_("Only a current holder of the Approver Designation may approve this report."))
            same_user_demo = (
                report.submitted_by_id == self.env.user
                and staging_self_approval_demo_enabled(self.env)
            )
            if report.submitted_by_id == self.env.user and not same_user_demo:
                raise ValidationError(_("The same user cannot submit and approve an inspection report."))
            if not report.effective_date:
                raise ValidationError(_("Effective Date is required before approval."))
            report.with_context(allow_native_form_workflow=True).write({
                "workflow_state": "approved",
                "approved_by_id": self.env.user.id,
            })
            if same_user_demo:
                record_staging_demo_transition(
                    report, "review", "approved", "staging_demo_approved"
                )


class HjigInspectionPoint(models.Model):
    _name = "hjig.inspection.point"
    _description = "Visual / Assembly Inspection Point"
    _order = "report_id, sequence, id"

    report_id = fields.Many2one("hjig.inspection.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="report_id.project_id", store=True, index=True)
    report_type = fields.Selection(related="report_id.report_type", store=True, readonly=True)
    sequence = fields.Integer(default=10)
    point_number = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"))
    description = fields.Text(required=True)
    checkpoint_master_id = fields.Many2one(
        "hjig.inspection.checkpoint.master",
        string="Controlled Checkpoint",
        ondelete="restrict",
        readonly=True,
        index=True,
    )
    category = fields.Char(related="checkpoint_master_id.category", store=True, readonly=True)
    phase = fields.Selection(related="checkpoint_master_id.phase", store=True, readonly=True)
    not_required = fields.Boolean(string="Not Required")
    picture = fields.Image(attachment=True)
    involved_part_ids = fields.Many2many("x_mould_part", string="Parts Involved")
    trial_result_ids = fields.One2many("hjig.inspection.trial.result", "point_id", string="Trial Results")

    _point_number_unique = models.Constraint(
        "UNIQUE(report_id, point_number)",
        "Inspection Point Number must be unique within the report.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            report = self.env["hjig.inspection.report"].browse(vals.get("report_id")).exists()
            if report.workflow_state != "draft":
                raise ValidationError(_("Inspection points may only be added to a Draft report."))
            if report.report_type == "dimensional":
                raise ValidationError(_("Inspection points cannot be added to a Dimensional report."))
            if not self.env.context.get("hjig_checkpoint_generation"):
                raise ValidationError(
                    _("Visual and Assembly checkpoints are generated only from the controlled master baseline.")
                )
            checkpoint = self.env["hjig.inspection.checkpoint.master"].browse(
                vals.get("checkpoint_master_id")
            ).exists()
            if not checkpoint:
                raise ValidationError(_("A controlled checkpoint master is required."))
            if checkpoint and checkpoint.form_kind != report.report_type:
                raise ValidationError(_("The controlled checkpoint belongs to a different inspection form."))
            vals.update({
                "sequence": checkpoint.sequence,
                "description": checkpoint.checkpoint_text,
                "not_required": checkpoint.default_not_required,
            })
            if vals.get("point_number", _("New")) == _("New"):
                prefix = "AP" if report.report_type == "assembly" else "VP"
                count = self.search_count([("report_id", "=", report.id)]) + 1
                vals["point_number"] = "%s%03d" % (prefix, count)
            record = super().create([vals])
            for stage, _label in TRIAL_STAGES:
                self.env["hjig.inspection.trial.result"].create({"point_id": record.id, "trial_stage": stage})
            records |= record
        return records

    @api.constrains("involved_part_ids", "report_id")
    def _check_involved_parts_project(self):
        for point in self:
            if point.involved_part_ids.filtered(lambda part: part.x_project_id != point.project_id):
                raise ValidationError(_("All involved parts must belong to the inspection report project."))

    def write(self, vals):
        if any(item.report_id.workflow_state != "draft" for item in self):
            raise ValidationError(_("Inspection points are editable only while the report is Draft."))
        governed = {"report_id", "checkpoint_master_id", "sequence", "point_number", "description"}
        if governed.intersection(vals) and self.filtered("checkpoint_master_id"):
            raise ValidationError(_("Controlled checkpoint identity and wording cannot be rewritten."))
        result = super().write(vals)
        if "not_required" in vals:
            if vals["not_required"]:
                self.trial_result_ids.write({"status": "na"})
            else:
                self.trial_result_ids.filtered(lambda item: item.status == "na").write({"status": "pending"})
        return result

    def unlink(self):
        if self.filtered("checkpoint_master_id"):
            raise UserError(_("Controlled baseline checkpoints cannot be deleted from an inspection report."))
        if any(item.report_id.workflow_state != "draft" for item in self):
            raise UserError(_("Inspection points may only be deleted while the report is Draft."))
        return super().unlink()


class HjigInspectionTrialResult(models.Model):
    _name = "hjig.inspection.trial.result"
    _description = "Inspection Trial Result"
    _order = "point_id, trial_stage"

    point_id = fields.Many2one("hjig.inspection.point", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="point_id.project_id", store=True, index=True)
    trial_stage = fields.Selection(TRIAL_STAGES, required=True)
    plan_date = fields.Date()
    actual_date = fields.Date()
    status = fields.Selection(
        [("pending", "Not Yet Checked"), ("pass", "Pass"), ("fail", "Fail"), ("na", "N/A")],
        default="pending",
        required=True,
    )
    remarks = fields.Text()

    _point_trial_unique = models.Constraint(
        "UNIQUE(point_id, trial_stage)",
        "Only one result per trial stage is allowed for each inspection point.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            point = self.env["hjig.inspection.point"].browse(vals.get("point_id")).exists()
            if point and point.report_id.workflow_state != "draft":
                raise ValidationError(_("Trial results may only be added to a Draft report."))
        return super().create(vals_list)

    def write(self, vals):
        if any(item.point_id.report_id.workflow_state != "draft" for item in self):
            raise ValidationError(_("Trial results are editable only while the report is Draft."))
        if vals.get("status") == "na" and any(not item.point_id.not_required for item in self):
            raise ValidationError(_("Only a checkpoint marked Not Required may use the N/A result."))
        if vals.get("status") not in (None, "pending"):
            for result in self:
                point = result.point_id
                if point.report_id.report_type == "assembly" and point.phase == "after" and not point.not_required:
                    blockers = point.report_id.point_ids.filtered(
                        lambda item: item.phase == "during" and not item.not_required
                    ).trial_result_ids.filtered(
                        lambda item: item.trial_stage == result.trial_stage and item.status != "pass"
                    )
                    if blockers:
                        raise ValidationError(
                            _("Complete every applicable During Assembly checkpoint as Pass before evaluating After Assembly Complete checkpoints for %s.")
                            % dict(TRIAL_STAGES).get(result.trial_stage, result.trial_stage)
                        )
        return super().write(vals)

    def unlink(self):
        if any(item.point_id.report_id.workflow_state != "draft" for item in self):
            raise UserError(_("Trial results may only be deleted while the report is Draft."))
        return super().unlink()


class HjigDimensionalLine(models.Model):
    _name = "hjig.dimensional.line"
    _description = "Dimensional Inspection Line"
    _order = "report_id, sequence, id"

    report_id = fields.Many2one("hjig.inspection.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="report_id.project_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    dimension_number = fields.Char(required=True)
    critical_dimension = fields.Boolean(string="Critical Dimension")
    drawing_dimension_mm = fields.Float(required=True, digits=(16, 4))
    tolerance_minus_mm = fields.Float(required=True, digits=(16, 4))
    tolerance_plus_mm = fields.Float(required=True, digits=(16, 4))
    min_dimension_mm = fields.Float(compute="_compute_limits", store=True, digits=(16, 4))
    max_dimension_mm = fields.Float(compute="_compute_limits", store=True, digits=(16, 4))
    method_used = fields.Selection(
        [
            ("digital_calliper", "Digital Calliper"), ("micrometer", "Micrometer"),
            ("height_gauge", "Height Gauge"), ("cmm", "CMM"),
            ("pin_gauge", "Pin Gauge"), ("profile_projector", "Profile Projector"),
            ("other", "Other"),
        ],
        required=True,
    )
    method_master_id = fields.Many2one(
        "hjig.inspection.method.master",
        string="Inspection Method",
        domain="[('state', '=', 'approved'), ('active', '=', True)]",
        ondelete="restrict",
    )
    measurement_ids = fields.One2many("hjig.dimensional.measurement", "dimension_line_id", string="Measurements")

    _report_dimension_unique = models.Constraint(
        "UNIQUE(report_id, dimension_number)",
        "Dimension Number must be unique within the report.",
    )

    @api.model
    def _method_snapshot_values(self, vals):
        vals = dict(vals)
        if vals.get("method_master_id"):
            method = self.env["hjig.inspection.method.master"].browse(vals["method_master_id"]).exists()
            if method:
                legacy_map = {
                    "digital calliper": "digital_calliper",
                    "micrometer": "micrometer",
                    "height gauge": "height_gauge",
                    "height guage": "height_gauge",
                    "pin gauge": "pin_gauge",
                    "pin gage": "pin_gauge",
                    "profile projector": "profile_projector",
                }
                vals["method_used"] = legacy_map.get(method.name.strip().lower(), "other")
        return vals

    @api.depends("drawing_dimension_mm", "tolerance_minus_mm", "tolerance_plus_mm")
    def _compute_limits(self):
        for line in self:
            line.min_dimension_mm = line.drawing_dimension_mm - line.tolerance_minus_mm
            line.max_dimension_mm = line.drawing_dimension_mm + line.tolerance_plus_mm

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._method_snapshot_values(vals) for vals in vals_list]
        for vals in vals_list:
            report = self.env["hjig.inspection.report"].browse(vals.get("report_id")).exists()
            if report and (report.workflow_state != "draft" or report.report_type != "dimensional"):
                raise ValidationError(_("Dimensions may only be added to a Draft Dimensional report."))
        return super().create(vals_list)

    @api.constrains("tolerance_minus_mm", "tolerance_plus_mm")
    def _check_tolerances(self):
        for line in self:
            if line.tolerance_minus_mm < 0 or line.tolerance_plus_mm < 0:
                raise ValidationError(_("Tolerance values must be entered as positive magnitudes."))

    @api.onchange("method_master_id")
    def _onchange_method_master_id(self):
        if self.method_master_id:
            legacy_map = {
                "digital calliper": "digital_calliper",
                "micrometer": "micrometer",
                "height gauge": "height_gauge",
                "height guage": "height_gauge",
                "pin gauge": "pin_gauge",
                "pin gage": "pin_gauge",
                "profile projector": "profile_projector",
            }
            self.method_used = legacy_map.get(self.method_master_id.name.strip().lower(), "other")

    def write(self, vals):
        if any(item.report_id.workflow_state != "draft" for item in self):
            raise ValidationError(_("Dimensions are editable only while the report is Draft."))
        return super().write(self._method_snapshot_values(vals))

    def unlink(self):
        if any(item.report_id.workflow_state != "draft" for item in self):
            raise UserError(_("Dimensions may only be deleted while the report is Draft."))
        return super().unlink()


class HjigDimensionalMeasurement(models.Model):
    _name = "hjig.dimensional.measurement"
    _description = "Cavity-wise Dimensional Measurement"
    _order = "dimension_line_id, trial_stage, cavity_number"

    dimension_line_id = fields.Many2one("hjig.dimensional.line", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="dimension_line_id.project_id", store=True, index=True)
    trial_stage = fields.Selection(TRIAL_STAGES, required=True)
    cavity_number = fields.Integer(required=True, default=1)
    measurement_taken = fields.Boolean(default=True)
    actual_dimension_mm = fields.Float(digits=(16, 4))
    result = fields.Selection([("go", "GO"), ("ng", "NG")], compute="_compute_result", store=True)
    remarks = fields.Char()

    _dimension_trial_cavity_unique = models.Constraint(
        "UNIQUE(dimension_line_id, trial_stage, cavity_number)",
        "Only one measurement is allowed per dimension, trial and cavity.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            line = self.env["hjig.dimensional.line"].browse(vals.get("dimension_line_id")).exists()
            if line and line.report_id.workflow_state != "draft":
                raise ValidationError(_("Measurements may only be added to a Draft report."))
        return super().create(vals_list)

    @api.depends(
        "measurement_taken", "actual_dimension_mm",
        "dimension_line_id.min_dimension_mm", "dimension_line_id.max_dimension_mm",
    )
    def _compute_result(self):
        for measurement in self:
            if not measurement.measurement_taken:
                measurement.result = False
            elif measurement.dimension_line_id.min_dimension_mm <= measurement.actual_dimension_mm <= measurement.dimension_line_id.max_dimension_mm:
                measurement.result = "go"
            else:
                measurement.result = "ng"

    @api.constrains("cavity_number")
    def _check_cavity_number(self):
        for measurement in self:
            if measurement.cavity_number <= 0:
                raise ValidationError(_("Cavity Number must be greater than zero."))

    def write(self, vals):
        if any(item.dimension_line_id.report_id.workflow_state != "draft" for item in self):
            raise ValidationError(_("Measurements are editable only while the report is Draft."))
        return super().write(vals)

    def unlink(self):
        if any(item.dimension_line_id.report_id.workflow_state != "draft" for item in self):
            raise UserError(_("Measurements may only be deleted while the report is Draft."))
        return super().unlink()


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_mould_plan_count = fields.Integer(compute="_compute_native_form_counts")
    hjig_inspection_report_count = fields.Integer(compute="_compute_native_form_counts")

    def _compute_native_form_counts(self):
        for project in self:
            project.hjig_mould_plan_count = self.env["x_mould"].search_count([("x_project_id", "=", project.id)])
            project.hjig_inspection_report_count = self.env["hjig.inspection.report"].search_count([("project_id", "=", project.id)])

    def write(self, vals):
        if "x_project_code" in vals:
            new_code = (vals.get("x_project_code") or "").strip().upper() or False
            for project in self:
                has_native_forms = self.env["x_mould"].search_count([("x_project_id", "=", project.id)])
                has_native_forms += self.env["hjig.inspection.report"].search_count([("project_id", "=", project.id)])
                has_native_forms += self.env["hjig.final.mould.plan"].search_count([("project_id", "=", project.id)])
                has_native_forms += self.env["hjig.project.risk"].search_count([("project_id", "=", project.id)])
                has_native_forms += self.env["hjig.project.issue"].search_count([("project_id", "=", project.id)])
                has_native_forms += self.env["hjig.project.ecn"].search_count([("project_id", "=", project.id)])
                if project.x_project_code != new_code and has_native_forms:
                    raise ValidationError(_("Project Code cannot be changed after native project forms exist."))
        return super().write(vals)

    def action_open_hjig_mould_plans(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("new_hongyijig_custom.action_hjig_mould_plan")
        action.update({"domain": [("x_project_id", "=", self.id)], "context": {"default_x_project_id": self.id}})
        return action

    def action_open_hjig_inspection_reports(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("new_hongyijig_custom.action_hjig_inspection_report")
        action.update({"domain": [("project_id", "=", self.id)], "context": {"default_project_id": self.id}})
        return action
