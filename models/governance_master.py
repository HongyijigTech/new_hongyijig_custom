# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HjigGovernanceDesignation(models.Model):
    _name = "hjig.governance.designation"
    _description = "Governance Designation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "category, code"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    category = fields.Selection(
        [
            ("governance", "Governance / PMO"),
            ("project", "Project Management"),
            ("engineering", "Engineering"),
            ("quality", "Quality"),
            ("commercial", "Commercial / Logistics"),
            ("customer", "Customer"),
            ("supplier", "Supplier / Toolmaker"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    holder_ids = fields.Many2many(
        "res.users",
        "hjig_designation_user_rel",
        "designation_id",
        "user_id",
        string="Current Role Holders",
        tracking=True,
        help="Users currently authorised to act for this designation. Approval authority follows the designation, not a hard-coded person.",
    )
    description = fields.Text()
    active = fields.Boolean(default=True, tracking=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Governance designation code must be unique.",
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
        return super().write(vals)


class HjigLaunchguardStage(models.Model):
    _name = "hjig.launchguard.stage"
    _description = "Programme Governance Stage"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, code"

    code = fields.Char(required=True, index=True, tracking=True)
    legacy_code = fields.Char(
        index=True,
        tracking=True,
        help="Legacy Studio/native-stage code retained for governed migration traceability.",
    )
    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(required=True, default=10, index=True)
    stage_type = fields.Selection(
        [
            ("activation", "Project Activation"),
            ("technical_gate", "Technical Gate"),
            ("advisory_session", "Advisory Session"),
            ("closure", "Project Closure"),
        ],
        required=True,
        default="technical_gate",
        tracking=True,
    )
    description = fields.Text()
    active = fields.Boolean(default=True, tracking=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "LaunchGuard stage code must be unique.",
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
        governed_fields = {"code", "legacy_code", "name", "sequence", "stage_type"}
        if governed_fields.intersection(vals) and self.env["hjig.project.document"].search_count([
            ("stage_id", "in", self.ids),
        ]):
            raise ValidationError(
                _("A stage used by a controlled document cannot be rewritten. Archive it and create a governed replacement.")
            )
        return super().write(vals)


class HjigGovernanceArtifactMaster(models.Model):
    _name = "hjig.governance.artifact.master"
    _description = "SOP and Form Master Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "artifact_type desc, code"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    artifact_type = fields.Selection(
        [("sop", "SOP"), ("form", "Form / Record")],
        required=True,
        index=True,
        tracking=True,
    )
    applicable_stage_ids = fields.Many2many(
        "hjig.launchguard.stage",
        "hjig_artifact_stage_rel",
        "artifact_id",
        "stage_id",
        string="Applicable Stages",
        required=True,
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    default_register_type = fields.Selection(
        [
            ("customer", "Customer Documents"),
            ("programme_internal", "Programme / Internal Documents"),
        ],
        required=True,
        default="programme_internal",
        tracking=True,
    )
    default_document_class = fields.Selection(
        [
            ("master_reference", "Master / Reference"),
            ("customer_controlled", "Customer-Controlled"),
            ("project_working", "Project Working Document"),
            ("evidence", "Evidence"),
            ("approved_deliverable", "Approved Deliverable"),
        ],
        required=True,
        default="project_working",
        tracking=True,
    )
    revision = fields.Char(required=True, default="1.0", tracking=True)
    mandatory = fields.Boolean(default=True, tracking=True)
    master_reference_url = fields.Char(string="Master Template / Reference Link", tracking=True)
    master_tab_name = fields.Char(string="Master Workbook Tab", tracking=True)
    description = fields.Text()
    active = fields.Boolean(default=True, tracking=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "SOP/Form Master code must be unique.",
    )

    @api.constrains("owner_designation_id", "approver_designation_id")
    def _check_designation_separation(self):
        for artifact in self:
            if artifact.owner_designation_id == artifact.approver_designation_id:
                raise ValidationError(
                    _("Owner and approver designations must be different.")
                )

    @api.constrains("applicable_stage_ids")
    def _check_applicable_stages(self):
        for artifact in self:
            if not artifact.applicable_stage_ids:
                raise ValidationError(_("Every SOP/Form Master must apply to at least one LaunchGuard stage."))

    @api.constrains("default_register_type", "default_document_class")
    def _check_default_classification(self):
        for artifact in self:
            if artifact.default_register_type == "customer" and artifact.default_document_class in (
                "master_reference",
                "project_working",
            ):
                raise ValidationError(
                    _("Customer-register masters cannot default to Master/Reference or Project Working.")
                )
            if (
                artifact.default_register_type == "programme_internal"
                and artifact.default_document_class == "customer_controlled"
            ):
                raise ValidationError(
                    _("Customer-controlled masters must use the Customer Document Register.")
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
        governed_fields = {
            "code", "name", "artifact_type", "applicable_stage_ids",
            "owner_designation_id", "approver_designation_id",
            "default_register_type", "default_document_class", "revision",
            "master_reference_url", "master_tab_name",
        }
        if governed_fields.intersection(vals) and self.env["hjig.project.document"].search_count([
            ("artifact_master_id", "in", self.ids),
        ]):
            raise ValidationError(
                _("An SOP/Form Master used by a controlled document cannot be rewritten. Archive it and create a new revision.")
            )
        return super().write(vals)
