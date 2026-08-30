# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import (
    record_staging_demo_transition,
    staging_self_approval_demo_enabled,
)


class HjigEngineeringReferenceMixin(models.AbstractModel):
    _name = "hjig.engineering.reference.mixin"
    _description = "Engineering Reference Governance"

    revision = fields.Char(required=True, default="WB-2026-08-21", tracking=True)
    source_workbook = fields.Char(
        required=True,
        default="Master WorkBook",
        readonly=True,
    )
    source_tab = fields.Char(required=True, readonly=True)
    source_row = fields.Integer(readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("superseded", "Superseded")],
        required=True,
        default="draft",
        index=True,
        tracking=True,
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env.ref(
            "new_hongyijig_custom.designation_tool_design", raise_if_not_found=False
        ),
        tracking=True,
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env.ref(
            "new_hongyijig_custom.designation_project_manager", raise_if_not_found=False
        ),
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    effective_date = fields.Date(readonly=True, copy=False, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    _reference_fields = set()

    @api.constrains("owner_designation_id", "approver_designation_id")
    def _check_separation_of_duties(self):
        for record in self:
            if record.owner_designation_id == record.approver_designation_id:
                raise ValidationError(_("Reference owner and approver designations must be different."))

    def write(self, vals):
        controlled = set(self._reference_fields) | {
            "revision", "source_workbook", "source_tab", "source_row",
            "owner_designation_id", "approver_designation_id",
        }
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.state in ("approved", "superseded")):
            if not self.env.context.get("allow_reference_workflow"):
                raise ValidationError(
                    _("An approved engineering reference cannot be rewritten. Supersede it and create a new revision.")
                )
        if "state" in vals and not self.env.context.get("allow_reference_workflow"):
            raise ValidationError(_("Use the controlled workflow buttons to change reference status."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.state != "draft"):
            raise UserError(_("Only Draft engineering references may be deleted."))
        return super().unlink()

    def action_approve(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only Draft references can be approved."))
            if self.env.user not in record.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may approve this reference."))
            same_user_demo = (
                self.env.user in record.owner_designation_id.holder_ids
                and staging_self_approval_demo_enabled(self.env)
            )
            if self.env.user in record.owner_designation_id.holder_ids and not same_user_demo:
                raise ValidationError(_("The same user cannot own and approve an engineering reference."))
            record.with_context(allow_reference_workflow=True).write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "effective_date": fields.Date.context_today(record),
            })
            if same_user_demo:
                record_staging_demo_transition(
                    record, "draft", "approved", "staging_demo_approved"
                )

    def action_supersede(self):
        for record in self:
            if record.state != "approved":
                raise UserError(_("Only Approved references can be superseded."))
            if self.env.user not in record.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may supersede this reference."))
            record.with_context(allow_reference_workflow=True).write({"state": "superseded", "active": False})


class HjigPlasticMaterialMaster(models.Model):
    _name = "hjig.plastic.material.master"
    _description = "Plastic Raw Material Master"
    _inherit = ["hjig.engineering.reference.mixin", "mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "code, name"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    recommended_tonnage = fields.Char()
    shrinkage_range = fields.Char(required=True)
    density = fields.Char()
    melt_temperature = fields.Char()
    air_vent_depth = fields.Char()

    _reference_fields = {
        "code", "name", "recommended_tonnage", "shrinkage_range", "density",
        "melt_temperature", "air_vent_depth",
    }
    _code_unique = models.Constraint("UNIQUE(code, revision)", "Material code and revision must be unique.")


class HjigSurfaceFinishMaster(models.Model):
    _name = "hjig.surface.finish.master"
    _description = "Surface Finish and Texture Master"
    _inherit = ["hjig.engineering.reference.mixin", "mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "finish_system, code"

    finish_system = fields.Selection(
        [("spi", "SPI"), ("vdi", "VDI"), ("special", "Special Texture")],
        required=True,
        index=True,
        tracking=True,
    )
    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    family = fields.Char()
    method = fields.Char()
    appearance = fields.Char()
    roughness_or_depth = fields.Char()
    gloss_or_category = fields.Char()
    recommended_draft = fields.Char()
    typical_applications = fields.Text()
    manufacturing_risk = fields.Char()
    tooling_notes = fields.Text()

    _reference_fields = {
        "finish_system", "code", "name", "family", "method", "appearance",
        "roughness_or_depth", "gloss_or_category", "recommended_draft",
        "typical_applications", "manufacturing_risk", "tooling_notes",
    }
    _code_unique = models.Constraint(
        "UNIQUE(finish_system, code, revision)",
        "Finish system, code and revision must be unique.",
    )

class HjigToolSteelMaster(models.Model):
    _name = "hjig.tool.steel.master"
    _description = "Tool Steel Master"
    _inherit = ["hjig.engineering.reference.mixin", "mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "manufacturer, grade"

    manufacturer = fields.Char(required=True, index=True, tracking=True)
    grade = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(compute="_compute_name", store=True)
    aisi_standard = fields.Char(string="AISI")
    jis_standard = fields.Char(string="JIS")
    wn_standard = fields.Char(string="W.Nr")
    delivered_hardness = fields.Char()
    characteristics = fields.Text()
    typical_analysis = fields.Text()
    applications = fields.Text()

    _reference_fields = {
        "manufacturer", "grade", "aisi_standard", "jis_standard", "wn_standard",
        "delivered_hardness", "characteristics", "typical_analysis", "applications",
    }
    _grade_unique = models.Constraint(
        "UNIQUE(manufacturer, grade, revision)",
        "Manufacturer, grade and revision must be unique.",
    )

    @api.depends("manufacturer", "grade")
    def _compute_name(self):
        for record in self:
            record.name = "%s - %s" % (record.manufacturer, record.grade)


class HjigGateTypeMaster(models.Model):
    _name = "hjig.gate.type.master"
    _description = "Runner and Gate Type Master"
    _inherit = ["hjig.engineering.reference.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "runner_type, name"

    runner_type = fields.Selection(
        [("cold", "Cold Runner"), ("hot", "Hot Runner"), ("hybrid", "Hybrid")],
        required=True,
        index=True,
        tracking=True,
    )
    name = fields.Char(required=True, index=True, tracking=True)
    common_name = fields.Char()
    best_part_size = fields.Char()
    typical_applications = fields.Text()
    suitable_materials = fields.Char()
    cosmetic_quality = fields.Char()
    automation_friendly = fields.Char()
    pressure_loss = fields.Char()
    tool_cost = fields.Char()
    advantages = fields.Text()
    risks = fields.Text()

    _reference_fields = {
        "runner_type", "name", "common_name", "best_part_size", "typical_applications",
        "suitable_materials", "cosmetic_quality", "automation_friendly", "pressure_loss",
        "tool_cost", "advantages", "risks",
    }
    _gate_unique = models.Constraint(
        "UNIQUE(runner_type, name, revision)",
        "Runner type, gate name and revision must be unique.",
    )


class HjigInspectionMethodMaster(models.Model):
    _name = "hjig.inspection.method.master"
    _description = "Inspection Method Master"
    _inherit = ["hjig.engineering.reference.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, index=True, tracking=True)
    method_category = fields.Selection(
        [("contact", "Contact"), ("gauge", "Gauge"), ("optical", "Optical / Scan"), ("visual", "Visual")],
        required=True,
        default="contact",
        tracking=True,
    )
    notes = fields.Text()

    _reference_fields = {"name", "method_category", "notes"}
    _name_unique = models.Constraint("UNIQUE(name, revision)", "Inspection method and revision must be unique.")
