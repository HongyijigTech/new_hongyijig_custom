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
        string="Template-Level Holders",
        tracking=True,
        help="Default authority for programme-template governance. Customer-project execution uses Project Designation Assignments instead.",
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

    def _holders_for_project(self, project):
        """Resolve authority inside one project; never leak global holders across projects."""
        self.ensure_one()
        if not project:
            return self.holder_ids
        assignment = self.env["hjig.project.designation.assignment"].search([
            ("project_id", "=", project.id),
            ("designation_id", "=", self.id),
            ("active", "=", True),
        ], limit=1)
        if not assignment:
            return self.env["res.users"]
        today = fields.Date.context_today(self)
        if assignment.effective_from and assignment.effective_from > today:
            return self.env["res.users"]
        if assignment.effective_to and assignment.effective_to < today:
            return self.env["res.users"]
        return assignment.holder_ids

    def _user_holds_for_project(self, user, project):
        self.ensure_one()
        return user in self._holders_for_project(project)


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
            ("milestone", "Route Milestone / Direct Entry Control"),
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
    source_document_name = fields.Char(
        string="Authority Source Document",
        tracking=True,
        help="Approved source containing the full operating procedure. The Odoo guidance is a concise execution aid, not a replacement for this authority source.",
    )
    source_page_from = fields.Integer(string="Source Page From", tracking=True)
    source_page_to = fields.Integer(string="Source Page To", tracking=True)
    employee_quick_guide = fields.Text(
        string="Employee Quick Guide",
        help="Short operating sequence for the employee. Evidence remains in the existing forms, registers and gate checklists.",
    )
    entry_control_summary = fields.Text(string="Entry Controls")
    hard_stop_summary = fields.Text(string="Hard Stops / Escalation")
    exit_control_summary = fields.Text(string="Exit Controls / Evidence")
    ai_reference_ready = fields.Boolean(
        string="AI Source Ready",
        compute="_compute_ai_reference_ready",
        help="Indicates that the SOP has an approved source range and concise operational guidance that a future governed AI assistant can cite.",
    )
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

    @api.depends(
        "artifact_type", "source_document_name", "source_page_from", "source_page_to",
        "employee_quick_guide", "entry_control_summary", "hard_stop_summary",
        "exit_control_summary",
    )
    def _compute_ai_reference_ready(self):
        for artifact in self:
            artifact.ai_reference_ready = bool(
                artifact.artifact_type == "sop"
                and artifact.source_document_name
                and artifact.source_page_from > 0
                and artifact.source_page_to >= artifact.source_page_from
                and artifact.employee_quick_guide
                and artifact.entry_control_summary
                and artifact.hard_stop_summary
                and artifact.exit_control_summary
            )

    @api.constrains("source_document_name", "source_page_from", "source_page_to")
    def _check_authority_source_range(self):
        for artifact in self:
            source_values = (
                bool(artifact.source_document_name),
                bool(artifact.source_page_from),
                bool(artifact.source_page_to),
            )
            if any(source_values) and not all(source_values):
                raise ValidationError(
                    _("Authority source document, first page and last page must be recorded together.")
                )
            if all(source_values) and (
                artifact.source_page_from < 1
                or artifact.source_page_to < artifact.source_page_from
            ):
                raise ValidationError(
                    _("Authority source pages must be positive and the last page cannot precede the first page.")
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
        guidance_fields = {
            "source_document_name", "source_page_from", "source_page_to",
            "employee_quick_guide", "entry_control_summary",
            "hard_stop_summary", "exit_control_summary",
        }
        governed_fields = {
            "code", "name", "artifact_type", "applicable_stage_ids",
            "owner_designation_id", "approver_designation_id",
            "default_register_type", "default_document_class", "revision",
            "master_reference_url", "master_tab_name",
            *guidance_fields,
        }
        governed_changes = governed_fields.intersection(vals)
        one_time_module_seed = bool(
            self.env.context.get("install_mode")
            and governed_changes
            and governed_changes.issubset(guidance_fields)
            and all(not any(artifact[field_name] for field_name in guidance_fields) for artifact in self)
        )
        if (
            governed_changes
            and not one_time_module_seed
            and self.env["hjig.project.document"].search_count([
                ("artifact_master_id", "in", self.ids),
            ])
        ):
            raise ValidationError(
                _("An SOP/Form Master used by a controlled document cannot be rewritten. Archive it and create a new revision.")
            )
        return super().write(vals)
