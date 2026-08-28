# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [
            ("hjig.checklist", "Checklist"),
            ("hjig.gate", "Gate"),
        ]


class HjigChecklistTemplate(models.Model):
    _name = "hjig.checklist.template"
    _description = "Hongyi Checklist Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "stage_id, code, version desc"
    _rec_name = "name"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    version = fields.Char(required=True, default="1.0", tracking=True)
    stage_id = fields.Many2one("hjig.launchguard.stage", required=True, ondelete="restrict", tracking=True)
    purpose = fields.Text(required=True)
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    item_ids = fields.One2many("hjig.checklist.template.item", "template_id", string="Checklist Items")
    active = fields.Boolean(default=True, tracking=True)

    _code_version_unique = models.Constraint(
        "UNIQUE(code, version)", "Checklist template code and version must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        governed = {"code", "name", "version", "stage_id", "purpose", "owner_designation_id"}
        if governed.intersection(vals) and self.env["hjig.checklist"].search_count([
            ("template_id", "in", self.ids),
        ]):
            raise ValidationError(_("A used checklist template is immutable. Create a new version."))
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)


class HjigChecklistTemplateItem(models.Model):
    _name = "hjig.checklist.template.item"
    _description = "Hongyi Checklist Template Item"
    _order = "template_id, sequence, id"

    template_id = fields.Many2one("hjig.checklist.template", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    item_code = fields.Char(required=True)
    title = fields.Char(required=True)
    instruction = fields.Text(required=True)
    blocking = fields.Boolean(default=True)
    evidence_required = fields.Boolean(default=True)
    source_record_type = fields.Selection(
        [
            ("live_record", "Read from live operational record"),
            ("confirmation", "Human confirmation"),
            ("exception", "Exception-only entry"),
        ],
        default="live_record",
        required=True,
        help="Use live records wherever possible so the checklist does not duplicate data entry.",
    )

    _template_item_unique = models.Constraint(
        "UNIQUE(template_id, item_code)", "Checklist item code must be unique within the template."
    )

    @api.model_create_multi
    def create(self, vals_list):
        template_ids = [vals.get("template_id") for vals in vals_list if vals.get("template_id")]
        if template_ids and self.env["hjig.checklist"].search_count([("template_id", "in", template_ids)]):
            raise ValidationError(_("Items cannot be added to a checklist template already in use."))
        return super().create(vals_list)

    def write(self, vals):
        if self.env["hjig.checklist.response"].search_count([("template_item_id", "in", self.ids)]):
            raise ValidationError(_("A checklist item already used in an execution is immutable."))
        return super().write(vals)

    def unlink(self):
        if self.env["hjig.checklist.response"].search_count([("template_item_id", "in", self.ids)]):
            raise UserError(_("A checklist item already used in an execution cannot be deleted."))
        return super().unlink()


class HjigChecklist(models.Model):
    _name = "hjig.checklist"
    _description = "Hongyi Checklist Execution"
    _inherit = ["mail.thread", "mail.activity.mixin", "hjig.target.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Checklist For")
    template_id = fields.Many2one("hjig.checklist.template", required=True, ondelete="restrict", tracking=True)
    stage_id = fields.Many2one(related="template_id.stage_id", store=True, readonly=True, index=True)
    gate_id = fields.Many2one("hjig.gate", ondelete="restrict", index=True)
    state = fields.Selection(
        [("draft", "Draft"), ("in_progress", "In Progress"), ("ready", "Ready"), ("closed", "Closed")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    response_ids = fields.One2many("hjig.checklist.response", "checklist_id", string="Responses")
    readiness = fields.Selection(
        [("incomplete", "Incomplete"), ("pass", "Pass"), ("warn", "Warning"), ("fail", "Fail")],
        compute="_compute_readiness", store=True, index=True,
    )
    blocking_summary = fields.Text(compute="_compute_readiness", store=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Checklist code must be unique.")

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.checklist") or _("New")
        records = super().create(vals_list)
        records._create_responses_from_template()
        return records

    def _create_responses_from_template(self):
        response_model = self.env["hjig.checklist.response"]
        for checklist in self:
            if checklist.response_ids:
                continue
            response_model.create([{
                "checklist_id": checklist.id,
                "template_item_id": item.id,
            } for item in checklist.template_id.item_ids])

    @api.constrains("target_ref", "project_id", "template_id", "gate_id")
    def _check_governance(self):
        for checklist in self:
            checklist._check_target_project(checklist.target_ref, checklist.project_id)
            if checklist.gate_id:
                if checklist.gate_id.project_id != checklist.project_id:
                    raise ValidationError(_("Checklist and gate must belong to the same project."))
                if checklist.gate_id.stage_id != checklist.stage_id:
                    raise ValidationError(_("Checklist template stage must match the gate stage."))

    @api.depends(
        "response_ids.result", "response_ids.template_item_id.blocking",
        "response_ids.template_item_id.evidence_required", "response_ids.evidence_ids",
    )
    def _compute_readiness(self):
        for checklist in self:
            if not checklist.response_ids:
                checklist.readiness = "incomplete"
                checklist.blocking_summary = _("Checklist has no response items.")
                continue
            blockers = []
            warnings = []
            incomplete = []
            for response in checklist.response_ids:
                item = response.template_item_id
                missing_evidence = item.evidence_required and not response.evidence_ids
                if response.result == "fail":
                    (blockers if item.blocking else warnings).append(item.item_code)
                elif response.result == "not_applicable" and item.blocking:
                    warnings.append(item.item_code)
                elif response.result == "pending" or missing_evidence:
                    (blockers if item.blocking else incomplete).append(item.item_code)
            if blockers:
                checklist.readiness = "fail"
                checklist.blocking_summary = _("Blocking items: %s") % ", ".join(blockers)
            elif incomplete:
                checklist.readiness = "incomplete"
                checklist.blocking_summary = _("Incomplete items: %s") % ", ".join(incomplete)
            elif warnings:
                checklist.readiness = "warn"
                checklist.blocking_summary = _("Non-blocking failures: %s") % ", ".join(warnings)
            else:
                checklist.readiness = "pass"
                checklist.blocking_summary = False

    def write(self, vals):
        if "state" in vals and not self.env.context.get("allow_hjig_checklist_workflow"):
            raise ValidationError(_("Checklist state may only change through workflow actions."))
        locked_fields = {"project_id", "target_ref", "template_id", "gate_id"}
        if locked_fields.intersection(vals) and any(record.state in ("ready", "closed") for record in self):
            raise ValidationError(_("Ready or Closed checklist identity is read-only."))
        return super().write(vals)

    def action_start(self):
        for checklist in self:
            if checklist.state != "draft":
                raise UserError(_("Only Draft checklists can start."))
            checklist.with_context(allow_hjig_checklist_workflow=True).write({"state": "in_progress"})

    def action_mark_ready(self):
        for checklist in self:
            if checklist.state not in ("draft", "in_progress"):
                raise UserError(_("Only an open checklist can be marked Ready."))
            if checklist.readiness not in ("pass", "warn"):
                raise ValidationError(checklist.blocking_summary or _("Checklist is not ready."))
            checklist.with_context(allow_hjig_checklist_workflow=True).write({"state": "ready"})


class HjigChecklistResponse(models.Model):
    _name = "hjig.checklist.response"
    _description = "Hongyi Checklist Response"
    _order = "checklist_id, template_item_id"

    checklist_id = fields.Many2one("hjig.checklist", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="checklist_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="checklist_id.company_id", store=True, readonly=True, index=True)
    template_item_id = fields.Many2one("hjig.checklist.template.item", required=True, ondelete="restrict")
    item_code = fields.Char(related="template_item_id.item_code", readonly=True)
    title = fields.Char(related="template_item_id.title", readonly=True)
    blocking = fields.Boolean(related="template_item_id.blocking", readonly=True)
    evidence_required = fields.Boolean(related="template_item_id.evidence_required", readonly=True)
    result = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("not_applicable", "Not Applicable")],
        default="pending", required=True, tracking=True,
    )
    evidence_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_checklist_response_evidence_rel", "response_id", "evidence_id", string="Evidence"
    )
    comments = fields.Text()
    verified_by_id = fields.Many2one("res.users", readonly=True)
    verified_date = fields.Datetime(readonly=True)

    _checklist_item_unique = models.Constraint(
        "UNIQUE(checklist_id, template_item_id)", "A checklist can contain each template item only once."
    )

    @api.constrains("template_item_id", "checklist_id", "evidence_ids")
    def _check_response_governance(self):
        for response in self:
            if response.template_item_id.template_id != response.checklist_id.template_id:
                raise ValidationError(_("Checklist response item must belong to the selected template."))
            if any(evidence.project_id != response.project_id for evidence in response.evidence_ids):
                raise ValidationError(_("Checklist evidence must belong to the same project."))

    def write(self, vals):
        if any(response.checklist_id.state in ("ready", "closed") for response in self):
            raise ValidationError(_("Responses are read-only after the checklist is Ready or Closed."))
        workflow_fields = {"result", "verified_by_id", "verified_date"}
        if workflow_fields.intersection(vals) and not self.env.context.get("allow_hjig_checklist_response"):
            raise ValidationError(_("Checklist results may only change through response actions."))
        return super().write(vals)

    def action_pass(self):
        self._record_result("pass")

    def action_fail(self):
        self._record_result("fail")

    def action_not_applicable(self):
        self._record_result("not_applicable")

    def _record_result(self, result):
        for response in self:
            if result == "pass" and response.evidence_required and not response.evidence_ids:
                raise ValidationError(_("Evidence is required before this item can pass."))
            if result == "not_applicable" and response.blocking and not (response.comments or "").strip():
                raise ValidationError(_("A reason is required when a blocking item is Not Applicable."))
            response.with_context(allow_hjig_checklist_response=True).write({
                "result": result,
                "verified_by_id": self.env.user.id,
                "verified_date": fields.Datetime.now(),
            })


class HjigGate(models.Model):
    _name = "hjig.gate"
    _description = "Hongyi Human Gate Decision"
    _inherit = ["mail.thread", "mail.activity.mixin", "hjig.target.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Gate For")
    stage_id = fields.Many2one("hjig.launchguard.stage", required=True, ondelete="restrict", index=True, tracking=True)
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    checklist_ids = fields.One2many("hjig.checklist", "gate_id", string="Gate Checklists")
    readiness = fields.Selection(
        [("incomplete", "Incomplete"), ("pass", "Pass"), ("warn", "Warning"), ("fail", "Fail")],
        compute="_compute_readiness", store=True, index=True,
    )
    blocking_summary = fields.Text(compute="_compute_readiness", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("pending", "Pending Decision"), ("go", "GO"), ("no_go", "NO-GO")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    cycle = fields.Integer(default=1, required=True, tracking=True)
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")
    decision_notes = fields.Text(tracking=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Gate code must be unique.")
    _project_stage_cycle_unique = models.Constraint(
        "UNIQUE(project_id, stage_id, cycle)", "Gate cycle must be unique within a project stage."
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.gate") or _("New")
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id")
    def _check_target(self):
        for gate in self:
            gate._check_target_project(gate.target_ref, gate.project_id)

    @api.depends("checklist_ids.readiness", "checklist_ids.state", "checklist_ids.blocking_summary")
    def _compute_readiness(self):
        for gate in self:
            if not gate.checklist_ids:
                gate.readiness = "incomplete"
                gate.blocking_summary = _("No gate checklists are linked.")
            elif any(item.readiness == "fail" for item in gate.checklist_ids):
                gate.readiness = "fail"
                gate.blocking_summary = "\n".join(gate.checklist_ids.filtered(
                    lambda item: item.readiness == "fail"
                ).mapped("blocking_summary"))
            elif any(item.state != "ready" for item in gate.checklist_ids):
                gate.readiness = "incomplete"
                gate.blocking_summary = _("All linked checklists must be marked Ready.")
            elif any(item.readiness == "warn" for item in gate.checklist_ids):
                gate.readiness = "warn"
                gate.blocking_summary = _("One or more checklists contain accepted non-blocking warnings.")
            else:
                gate.readiness = "pass"
                gate.blocking_summary = False

    def write(self, vals):
        workflow_fields = {"state", "approval_id"}
        if workflow_fields.intersection(vals) and not self.env.context.get("allow_hjig_gate_workflow"):
            raise ValidationError(_("Gate decision fields may only change through the controlled workflow."))
        governed = {"project_id", "target_ref", "stage_id", "cycle", "approval_authority_designation_id"}
        if governed.intersection(vals) and any(gate.state in ("pending", "go", "no_go") for gate in self):
            raise ValidationError(_("Gate identity is read-only after decision request."))
        return super().write(vals)

    def action_request_decision(self):
        for gate in self:
            if gate.state != "draft":
                raise UserError(_("Only Draft gates can request a decision."))
            if gate.readiness not in ("pass", "warn"):
                raise ValidationError(gate.blocking_summary or _("Gate is not ready."))
            approval = self.env["hjig.approval"].create({
                "project_id": gate.project_id.id,
                "target_ref": "%s,%s" % (gate._name, gate.id),
                "approval_type": "gate",
                "authority_designation_id": gate.approval_authority_designation_id.id,
                "requested_by_id": self.env.user.id,
            })
            gate.with_context(allow_hjig_gate_workflow=True).write({
                "state": "pending", "approval_id": approval.id,
            })

    def action_apply_decision(self):
        for gate in self:
            if gate.state != "pending" or not gate.approval_id:
                raise UserError(_("The gate has no pending approval decision."))
            if gate.approval_id.state == "approved":
                next_state = "go"
            elif gate.approval_id.state == "rejected":
                next_state = "no_go"
            else:
                raise UserError(_("The gate approval decision is still pending."))
            gate.with_context(allow_hjig_gate_workflow=True).write({"state": next_state})
            gate.checklist_ids.with_context(allow_hjig_checklist_workflow=True).write({"state": "closed"})
            self.env["hjig.transition.log"].sudo().create({
                "project_id": gate.project_id.id,
                "target_ref": "%s,%s" % (gate._name, gate.id),
                "from_state": "pending", "to_state": next_state,
                "decision": gate.approval_id.state,
                "actor_id": self.env.user.id,
                "approval_id": gate.approval_id.id,
                "reason": gate.approval_id.decision_reason,
            })
