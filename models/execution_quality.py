# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


TOOLING_REPORT_TYPES = [
    ("kickoff", "Tooling Kick-off"),
    ("manufacturing_plan", "Tool Manufacturing Plan"),
    ("weekly_progress", "Weekly Tooling Progress"),
    ("milestone", "Milestone Completion"),
    ("steel_verification", "Steel Verification"),
    ("photo_evidence", "Photo / Video Evidence Log"),
    ("delay_recovery", "Delay and Recovery Plan"),
    ("supplier_action", "Supplier Action Update"),
    ("trial_readiness", "Trial Readiness"),
    ("trial", "Trial Report"),
    ("handover_dossier", "Tool Handover Dossier"),
]

MOULD_PLAN_REFERENCE_MODELS = [
    ("hjig.final.mould.plan", "Final Mould Plan"),
    ("x_mould", "Project Mould Planning Form"),
    ("hjig.mould.register", "Project Mould Register"),
]

PART_REFERENCE_MODELS = [
    ("x_mould_part", "Mould Planning Component / Part"),
    ("hjig.sourcebridge.component", "SourceBridge Sourcing Component"),
]


def _available_reference_models(recordset, candidates):
    """Expose database-native adapters without making them hard module dependencies."""
    return [(model, label) for model, label in candidates if model in recordset.env.registry]


def _reference_project(record):
    """Read the project from either governed or legacy Studio-backed records."""
    return getattr(record, "project_id", False) or getattr(record, "x_project_id", False)


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [
            ("hjig.tooling.execution", "Tooling Execution"),
            ("hjig.tooling.report", "Tooling Report"),
            ("hjig.tooling.action", "Tooling Action"),
            ("hjig.inspection", "Inspection"),
        ]


class HjigToolingExecution(models.Model):
    _name = "hjig.tooling.execution"
    _description = "Hongyi Tooling Execution"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    supplier_id = fields.Many2one("res.partner", required=True, ondelete="restrict", index=True, tracking=True)
    mould_plan_ref = fields.Reference(
        selection="_selection_mould_plan_ref_model",
        string="Linked Mould Plan",
        tracking=True,
        help="Link the existing authoritative Mould Planning or frozen Mould Plan record when available.",
    )
    mould_plan_reference = fields.Char(
        string="External / Legacy Mould Plan Reference",
        tracking=True,
        help="Fallback identifier only when the authoritative Mould Planning record is outside this Odoo database.",
    )
    supplier_order_reference = fields.Char(string="Supplier PO / Work Order", tracking=True)
    start_date = fields.Date(required=True, tracking=True)
    baseline_trial_date = fields.Date(required=True, tracking=True)
    current_forecast_trial_date = fields.Date(required=True, tracking=True)
    coordinator_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    state = fields.Selection(
        [("planned", "Planned"), ("active", "Active"), ("trial", "Trial"), ("handover", "Handover"), ("closed", "Closed")],
        default="planned", required=True, copy=False, index=True, tracking=True,
    )
    report_ids = fields.One2many("hjig.tooling.report", "execution_id", string="Execution Reports")
    action_ids = fields.One2many("hjig.tooling.action", "execution_id", string="Supplier Actions")
    latest_progress_percent = fields.Float(compute="_compute_execution_summary")
    open_action_count = fields.Integer(compute="_compute_execution_summary")
    delay_days = fields.Integer(compute="_compute_execution_summary")

    _code_unique = models.Constraint("UNIQUE(code)", "Tooling execution code must be unique.")

    @api.model
    def _selection_mould_plan_ref_model(self):
        return _available_reference_models(self, MOULD_PLAN_REFERENCE_MODELS)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "planned"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.tooling.execution") or _("New")
        return super().create(vals_list)

    @api.depends(
        "report_ids.report_type", "report_ids.state", "report_ids.actual_progress_percent",
        "action_ids.state", "baseline_trial_date", "current_forecast_trial_date",
    )
    def _compute_execution_summary(self):
        for execution in self:
            progress_reports = execution.report_ids.filtered(
                lambda report: report.report_type == "weekly_progress" and report.state == "approved"
            ).sorted("report_date", reverse=True)
            execution.latest_progress_percent = progress_reports[:1].actual_progress_percent if progress_reports else 0.0
            execution.open_action_count = len(execution.action_ids.filtered(lambda action: action.state != "closed"))
            if execution.baseline_trial_date and execution.current_forecast_trial_date:
                execution.delay_days = max((execution.current_forecast_trial_date - execution.baseline_trial_date).days, 0)
            else:
                execution.delay_days = 0

    @api.constrains("baseline_trial_date", "current_forecast_trial_date", "start_date")
    def _check_dates(self):
        for execution in self:
            if execution.baseline_trial_date < execution.start_date:
                raise ValidationError(_("Baseline trial date cannot be before tooling start."))
            if execution.current_forecast_trial_date < execution.start_date:
                raise ValidationError(_("Forecast trial date cannot be before tooling start."))

    @api.constrains("project_id", "mould_plan_ref", "mould_plan_reference")
    def _check_mould_plan_reference(self):
        for execution in self:
            if not execution.mould_plan_ref and not (execution.mould_plan_reference or "").strip():
                raise ValidationError(_("Link the authoritative Mould Plan or enter an external reference."))
            if execution.mould_plan_ref:
                reference_project = _reference_project(execution.mould_plan_ref)
                if reference_project and reference_project != execution.project_id:
                    raise ValidationError(_("The linked Mould Plan must belong to the same project."))

    def write(self, vals):
        if "state" in vals and not is_workflow_context(self.env):
            raise ValidationError(_("Tooling state may only change through workflow actions."))
        return super().write(vals)

    def _check_coordinator_authority(self):
        for execution in self:
            if execution.coordinator_id != self.env.user and not self.env.user.has_group("project.group_project_manager"):
                raise UserError(_("Only the Tooling Coordinator or a Project Manager may change execution stage."))

    def _log_transition(self, from_state, to_state, decision):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state, "to_state": to_state, "decision": decision,
            "actor_id": self.env.user.id,
        })

    def action_start(self):
        self._check_coordinator_authority()
        for execution in self:
            if execution.state != "planned":
                raise UserError(_("Only Planned tooling executions can start."))
            kickoff = execution.report_ids.filtered(lambda report: report.report_type == "kickoff" and report.state == "approved")
            plan = execution.report_ids.filtered(lambda report: report.report_type == "manufacturing_plan" and report.state == "approved")
            if not kickoff or not plan:
                raise ValidationError(_("Approved Kick-off and Manufacturing Plan reports are required before tooling starts."))
            execution.with_context(**workflow_context()).write({"state": "active"})
            execution._log_transition("planned", "active", "tooling_started")

    def action_start_trial(self):
        self._check_coordinator_authority()
        for execution in self:
            if execution.state != "active":
                raise UserError(_("Only Active tooling executions can enter Trial."))
            readiness = execution.report_ids.filtered(
                lambda report: report.report_type == "trial_readiness" and report.state == "approved"
            )
            if not readiness:
                raise ValidationError(_("An approved Trial Readiness report is required."))
            execution.with_context(**workflow_context()).write({"state": "trial"})
            execution._log_transition("active", "trial", "trial_started")

    def action_start_handover(self):
        self._check_coordinator_authority()
        for execution in self:
            if execution.state != "trial":
                raise UserError(_("Only Trial-stage tooling executions can enter Handover."))
            approved_trial = execution.report_ids.filtered(
                lambda report: report.report_type == "trial" and report.state == "approved" and report.trial_result in ("pass", "conditional")
            )
            if not approved_trial:
                raise ValidationError(_("An approved passing or conditional Trial Report is required."))
            execution.with_context(**workflow_context()).write({"state": "handover"})
            execution._log_transition("trial", "handover", "handover_started")

    def action_close(self):
        self._check_coordinator_authority()
        for execution in self:
            if execution.state != "handover":
                raise UserError(_("Only Handover-stage tooling executions can close."))
            dossier = execution.report_ids.filtered(
                lambda report: report.report_type == "handover_dossier" and report.state == "approved"
            )
            if not dossier:
                raise ValidationError(_("An approved Tool Handover Dossier is required."))
            if execution.action_ids.filtered(lambda action: action.state != "closed"):
                raise ValidationError(_("All supplier actions must be closed before tooling closure."))
            execution.with_context(**workflow_context()).write({"state": "closed"})
            execution._log_transition("handover", "closed", "tooling_closed")

    def unlink(self):
        if any(execution.state != "planned" or execution.report_ids or execution.action_ids for execution in self):
            raise UserError(_("Started tooling executions and their history cannot be deleted."))
        return super().unlink()


class HjigToolingReport(models.Model):
    _name = "hjig.tooling.report"
    _description = "Hongyi Tooling Execution Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "execution_id, report_date desc, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    execution_id = fields.Many2one("hjig.tooling.execution", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="execution_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="execution_id.company_id", store=True, readonly=True, index=True)
    supplier_id = fields.Many2one(related="execution_id.supplier_id", store=True, readonly=True, index=True)
    report_type = fields.Selection(TOOLING_REPORT_TYPES, required=True, index=True, tracking=True)
    report_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    reporting_period = fields.Char(help="Week number, milestone, or trial number as applicable.", tracking=True)
    planned_progress_percent = fields.Float(tracking=True)
    actual_progress_percent = fields.Float(tracking=True)
    current_operation = fields.Char(tracking=True)
    completed_work = fields.Text(tracking=True)
    issues = fields.Text(tracking=True)
    next_plan = fields.Text(tracking=True)
    recovery_action = fields.Text(tracking=True)
    revised_date = fields.Date(tracking=True)
    steel_grade_declared = fields.Char(tracking=True)
    steel_certificate_reference = fields.Char(tracking=True)
    trial_conditions = fields.Text(tracking=True)
    trial_result = fields.Selection([("pass", "Pass"), ("conditional", "Conditional"), ("fail", "Fail")], tracking=True)
    evidence_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_tooling_report_evidence_rel", "report_id", "evidence_id", string="Evidence"
    )
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")

    _code_unique = models.Constraint("UNIQUE(code)", "Tooling report code must be unique.")
    _period_unique = models.Constraint(
        "UNIQUE(execution_id, report_type, reporting_period)",
        "This reporting period already exists for the tooling execution and report type.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.tooling.report") or _("New")
        return super().create(vals_list)

    @api.constrains("planned_progress_percent", "actual_progress_percent")
    def _check_percentages(self):
        for report in self:
            if not 0 <= report.planned_progress_percent <= 100 or not 0 <= report.actual_progress_percent <= 100:
                raise ValidationError(_("Progress percentages must be between 0 and 100."))

    @api.constrains("evidence_ids", "project_id")
    def _check_evidence_project(self):
        for report in self:
            if any(evidence.project_id != report.project_id for evidence in report.evidence_ids):
                raise ValidationError(_("Tooling report evidence must belong to the same project."))

    def write(self, vals):
        workflow = {"state", "approval_id"}
        if workflow.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Tooling report approval fields may only change through workflow actions."))
        if any(report.state in ("review", "approved") for report in self):
            allowed = workflow if is_workflow_context(self.env) else {"message_follower_ids"}
            if set(vals) - allowed:
                raise ValidationError(_("Submitted tooling reports are read-only. Reject or create a correction report."))
        return super().write(vals)

    def _check_submission(self):
        evidence_required = {
            "kickoff", "weekly_progress", "milestone", "steel_verification", "photo_evidence",
            "trial_readiness", "trial", "handover_dossier",
        }
        for report in self:
            if report.report_type in evidence_required and not report.evidence_ids:
                raise ValidationError(_("This tooling report type requires evidence."))
            if report.evidence_ids:
                report.evidence_ids._assert_accepted()
            if report.report_type == "weekly_progress" and not report.next_plan:
                raise ValidationError(_("Weekly progress reports require the next-period plan."))
            if report.report_type in ("weekly_progress", "milestone", "trial") and not report.reporting_period:
                raise ValidationError(_("Weekly, milestone, and trial reports require a reporting period or event number."))
            if report.report_type == "delay_recovery" and (not report.recovery_action or not report.revised_date):
                raise ValidationError(_("Delay and Recovery reports require recovery actions and a revised date."))
            if report.report_type == "steel_verification" and (
                not report.steel_grade_declared or not report.steel_certificate_reference
            ):
                raise ValidationError(_("Steel Verification requires grade and certificate reference."))

    def action_submit_review(self):
        self._check_submission()
        for report in self:
            if report.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected reports can be submitted."))
            previous_state = report.state
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": report.project_id.id,
                "target_ref": "%s,%s" % (report._name, report.id),
                "approval_type": "engineering",
                "authority_designation_id": report.approval_authority_designation_id.id,
                "requested_by_id": self.env.user.id,
            })
            report.with_context(**workflow_context()).write({
                "state": "review", "approval_id": approval.id,
            })
            report._log_transition(previous_state, "review", "submitted", approval)

    def action_apply_decision(self):
        for report in self:
            if report.state != "review" or not report.approval_id:
                raise UserError(_("The report has no approval decision to apply."))
            if report.approval_id.state == "approved":
                report._check_submission()
                result = "approved"
            elif report.approval_id.state == "rejected":
                result = "rejected"
            else:
                raise UserError(_("The approval decision is still pending."))
            report.with_context(**workflow_context()).write({"state": result})
            report._log_transition("review", result, report.approval_id.state, report.approval_id)

    def _log_transition(self, from_state, to_state, decision, approval=False):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state, "to_state": to_state, "decision": decision,
            "actor_id": self.env.user.id, "approval_id": approval.id if approval else False,
        })

    def unlink(self):
        if any(report.state != "draft" for report in self):
            raise UserError(_("Submitted tooling reports cannot be deleted."))
        return super().unlink()


class HjigToolingAction(models.Model):
    _name = "hjig.tooling.action"
    _description = "Hongyi Supplier Tooling Action"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date, id"

    execution_id = fields.Many2one("hjig.tooling.execution", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="execution_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="execution_id.company_id", store=True, readonly=True, index=True)
    title = fields.Char(required=True, tracking=True)
    source_report_id = fields.Many2one("hjig.tooling.report", ondelete="restrict", tracking=True)
    owner_id = fields.Many2one("res.users", required=True, tracking=True)
    due_date = fields.Date(required=True, tracking=True)
    severity = fields.Selection(
        [("critical", "Critical"), ("high", "High"), ("normal", "Normal"), ("low", "Low")],
        default="normal", required=True, tracking=True,
    )
    state = fields.Selection(
        [("open", "Open"), ("in_progress", "In Progress"), ("verification", "Pending Verification"), ("closed", "Closed")],
        default="open", required=True, tracking=True,
    )
    closure_evidence_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_tooling_action_evidence_rel", "action_id", "evidence_id", string="Closure Evidence"
    )
    notes = fields.Text()

    @api.constrains("source_report_id", "execution_id", "closure_evidence_ids")
    def _check_links(self):
        for action in self:
            if action.source_report_id and action.source_report_id.execution_id != action.execution_id:
                raise ValidationError(_("Source report must belong to the same tooling execution."))
            if any(evidence.project_id != action.project_id for evidence in action.closure_evidence_ids):
                raise ValidationError(_("Action evidence must belong to the same project."))

    def action_close(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver"):
            raise UserError(_("Only an authorised Governance Approver may verify and close supplier actions."))
        for action in self:
            if action.state != "verification":
                raise UserError(_("Only actions Pending Verification can close."))
            if not action.closure_evidence_ids:
                raise ValidationError(_("Closure evidence is required before closing a supplier action."))
            action.closure_evidence_ids._assert_accepted()
            action.with_context(**workflow_context()).write({"state": "closed"})
            action._log_transition("verification", "closed", "verified_closed")

    def action_start(self):
        for action in self:
            if action.owner_id != self.env.user and not self.env.user.has_group("project.group_project_manager"):
                raise UserError(_("Only the Action Owner or a Project Manager may start this action."))
            if action.state != "open":
                raise UserError(_("Only Open actions can start."))
            action.with_context(**workflow_context()).write({"state": "in_progress"})
            action._log_transition("open", "in_progress", "started")

    def action_request_verification(self):
        for action in self:
            if action.owner_id != self.env.user and not self.env.user.has_group("project.group_project_manager"):
                raise UserError(_("Only the Action Owner or a Project Manager may request verification."))
            if action.state != "in_progress":
                raise UserError(_("Only In Progress actions can request verification."))
            if not action.closure_evidence_ids:
                raise ValidationError(_("Closure evidence is required before verification."))
            action.with_context(**workflow_context()).write({"state": "verification"})
            action._log_transition("in_progress", "verification", "verification_requested")

    def _log_transition(self, from_state, to_state, decision):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state, "to_state": to_state, "decision": decision,
            "actor_id": self.env.user.id,
        })

    def write(self, vals):
        if "state" in vals and not is_workflow_context(self.env):
            raise ValidationError(_("Tooling action state may only change through workflow actions."))
        if any(action.state == "closed" for action in self):
            allowed = {"state"} if is_workflow_context(self.env) else set()
            if set(vals) - allowed:
                raise ValidationError(_("Verified-closed supplier actions are immutable. Create a governed correction action."))
        return super().write(vals)

    def unlink(self):
        if any(action.state != "open" for action in self):
            raise UserError(_("Started or closed supplier actions cannot be deleted."))
        return super().unlink()


class HjigInspection(models.Model):
    _name = "hjig.inspection"
    _description = "Hongyi Inspection Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, inspection_date desc, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    inspection_type = fields.Selection(
        [
            ("part_visual", "Part Visual Inspection"),
            ("assembly", "Assembly Inspection"),
            ("dimensional", "Dimensional Inspection"),
            ("mould_pre_shipment", "Mould Pre-Shipment Inspection"),
        ],
        required=True, index=True, tracking=True,
    )
    supplier_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    supplier_order_reference = fields.Char(string="Supplier PO / Work Order", tracking=True)
    part_or_assembly_ref = fields.Reference(
        selection="_selection_part_reference_model",
        string="Linked Part / Assembly",
        tracking=True,
        help="Link the existing authoritative Mould Planning Part or SourceBridge Component when available.",
    )
    part_or_assembly_reference = fields.Char(
        string="External / Legacy Part or Assembly Reference",
        tracking=True,
        help="Fallback identifier only when the authoritative Part/Assembly record is outside this Odoo database.",
    )
    batch_reference = fields.Char(required=True, tracking=True)
    drawing_revision = fields.Char(required=True, tracking=True)
    inspection_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    inspector_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    line_ids = fields.One2many("hjig.inspection.line", "inspection_id", string="Inspection Characteristics")
    overall_result = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("conditional", "Conditional"), ("fail", "Fail")],
        compute="_compute_overall_result", store=True, index=True,
    )
    disposition = fields.Selection(
        [("accept", "Accept"), ("conditional", "Conditional Acceptance"), ("reject", "Reject")], tracking=True
    )
    disposition_reason = fields.Text(tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")

    _code_unique = models.Constraint("UNIQUE(code)", "Inspection code must be unique.")

    @api.model
    def _selection_part_reference_model(self):
        return _available_reference_models(self, PART_REFERENCE_MODELS)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.inspection") or _("New")
        return super().create(vals_list)

    @api.depends("line_ids.result")
    def _compute_overall_result(self):
        for inspection in self:
            if not inspection.line_ids or any(line.result == "pending" for line in inspection.line_ids):
                inspection.overall_result = "pending"
            elif any(line.result == "fail" and line.critical for line in inspection.line_ids):
                inspection.overall_result = "fail"
            elif any(line.result == "fail" for line in inspection.line_ids):
                inspection.overall_result = "conditional"
            else:
                inspection.overall_result = "pass"

    @api.constrains("project_id", "part_or_assembly_ref", "part_or_assembly_reference")
    def _check_part_reference(self):
        for inspection in self:
            if not inspection.part_or_assembly_ref and not (inspection.part_or_assembly_reference or "").strip():
                raise ValidationError(_("Link the authoritative Part/Assembly or enter an external reference."))
            if inspection.part_or_assembly_ref:
                reference_project = _reference_project(inspection.part_or_assembly_ref)
                if reference_project and reference_project != inspection.project_id:
                    raise ValidationError(_("The linked Part/Assembly must belong to the same project."))

    def write(self, vals):
        workflow = {"state", "approval_id"}
        if workflow.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Inspection approval fields may only change through workflow actions."))
        if any(record.state in ("review", "approved") for record in self):
            allowed = workflow if is_workflow_context(self.env) else set()
            if set(vals) - allowed:
                raise ValidationError(_("Inspection reports are read-only after review begins."))
        return super().write(vals)

    def action_submit_review(self):
        for inspection in self:
            if inspection.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected inspections can be submitted."))
            previous_state = inspection.state
            if not inspection.line_ids:
                raise ValidationError(_("At least one inspection characteristic is required."))
            if inspection.overall_result == "pending":
                raise ValidationError(_("Every inspection characteristic must have a result."))
            if any(not line.evidence_ids for line in inspection.line_ids):
                raise ValidationError(_("Every inspection characteristic requires evidence."))
            inspection.line_ids.mapped("evidence_ids")._assert_accepted()
            if not inspection.disposition:
                raise ValidationError(_("Inspection disposition is required before review."))
            if inspection.overall_result in ("conditional", "fail") and not inspection.disposition_reason:
                raise ValidationError(_("Conditional or failed inspection requires a disposition reason."))
            allowed_dispositions = {
                "pass": ("accept",),
                "conditional": ("conditional", "reject"),
                "fail": ("reject",),
            }
            if inspection.disposition not in allowed_dispositions[inspection.overall_result]:
                raise ValidationError(_("Inspection disposition conflicts with the calculated overall result."))
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": inspection.project_id.id,
                "target_ref": "%s,%s" % (inspection._name, inspection.id),
                "approval_type": "engineering",
                "authority_designation_id": inspection.approval_authority_designation_id.id,
                "requested_by_id": self.env.user.id,
            })
            inspection.with_context(**workflow_context()).write({
                "state": "review", "approval_id": approval.id,
            })
            inspection._log_transition(previous_state, "review", "submitted", approval)

    def action_apply_decision(self):
        for inspection in self:
            if inspection.state != "review" or not inspection.approval_id:
                raise UserError(_("The inspection has no approval decision to apply."))
            if inspection.approval_id.state == "approved":
                next_state = "approved"
            elif inspection.approval_id.state == "rejected":
                next_state = "rejected"
            else:
                raise UserError(_("The inspection approval is still pending."))
            inspection.with_context(**workflow_context()).write({"state": next_state})
            inspection._log_transition("review", next_state, inspection.approval_id.state, inspection.approval_id)

    def _log_transition(self, from_state, to_state, decision, approval=False):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state, "to_state": to_state, "decision": decision,
            "actor_id": self.env.user.id, "approval_id": approval.id if approval else False,
        })

    def unlink(self):
        if any(inspection.state != "draft" for inspection in self):
            raise UserError(_("Submitted inspection reports cannot be deleted."))
        return super().unlink()


class HjigInspectionLine(models.Model):
    _name = "hjig.inspection.line"
    _description = "Hongyi Inspection Characteristic"
    _order = "inspection_id, sequence, id"

    inspection_id = fields.Many2one("hjig.inspection", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="inspection_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="inspection_id.company_id", store=True, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    characteristic_code = fields.Char(required=True)
    requirement_id = fields.Many2one("hjig.sor.requirement", ondelete="restrict")
    check_type = fields.Selection(
        [("visual", "Visual"), ("assembly", "Assembly / Function"), ("dimensional", "Dimensional"), ("document", "Document / Accessory")],
        required=True,
    )
    description = fields.Char(required=True)
    critical = fields.Boolean(default=False)
    nominal = fields.Float()
    lower_limit = fields.Float()
    upper_limit = fields.Float()
    measured_value = fields.Float()
    measurement_recorded = fields.Boolean(default=False)
    unit = fields.Char()
    instrument_reference = fields.Char()
    result = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("not_applicable", "Not Applicable")],
        default="pending", required=True,
    )
    defect_location = fields.Char()
    defect_severity = fields.Selection([("critical", "Critical"), ("major", "Major"), ("minor", "Minor")])
    evidence_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_inspection_line_evidence_rel", "line_id", "evidence_id", string="Evidence"
    )
    notes = fields.Text()

    _inspection_characteristic_unique = models.Constraint(
        "UNIQUE(inspection_id, characteristic_code)", "Characteristic code must be unique within the inspection."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            inspection = self.env["hjig.inspection"].browse(vals.get("inspection_id")).exists()
            if inspection and inspection.state in ("review", "approved"):
                raise ValidationError(_("Inspection characteristics cannot be added after review begins."))
        return super().create(vals_list)

    @api.constrains("requirement_id", "inspection_id", "evidence_ids")
    def _check_links(self):
        for line in self:
            if line.requirement_id and line.requirement_id.project_id != line.project_id:
                raise ValidationError(_("SOR requirement must belong to the same project."))
            if any(evidence.project_id != line.project_id for evidence in line.evidence_ids):
                raise ValidationError(_("Inspection evidence must belong to the same project."))

    @api.constrains(
        "check_type", "lower_limit", "upper_limit", "measured_value", "measurement_recorded",
        "unit", "instrument_reference", "result", "notes",
    )
    def _check_dimensional_result(self):
        for line in self:
            if line.check_type == "dimensional":
                if not line.measurement_recorded or not line.unit or not line.instrument_reference:
                    raise ValidationError(_("Dimensional checks require a recorded measurement, unit, and instrument reference."))
                if line.lower_limit > line.upper_limit:
                    raise ValidationError(_("Dimensional lower limit cannot exceed upper limit."))
                calculated = "pass" if line.lower_limit <= line.measured_value <= line.upper_limit else "fail"
                if line.result not in ("pending", calculated):
                    raise ValidationError(_("Dimensional PASS/FAIL must match the recorded limits and measurement."))
            if line.result == "not_applicable" and not (line.notes or "").strip():
                raise ValidationError(_("Not Applicable inspection characteristics require a reason."))

    def write(self, vals):
        if any(line.inspection_id.state in ("review", "approved") for line in self):
            raise ValidationError(_("Inspection characteristics are read-only after review begins."))
        return super().write(vals)

    def unlink(self):
        if any(line.inspection_id.state in ("review", "approved") for line in self):
            raise UserError(_("Inspection characteristics cannot be deleted after review begins."))
        return super().unlink()
