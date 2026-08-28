# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [
            ("hjig.knowledge.item", "Engineering Knowledge Item"),
            ("hjig.ai.assistance.log", "AI Assistance Log"),
        ]


class HjigKnowledgeItem(models.Model):
    _name = "hjig.knowledge.item"
    _description = "Hongyi Engineering Knowledge Item"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "category, code, version desc"
    _rec_name = "title"

    code = fields.Char(required=True, index=True, tracking=True)
    project_id = fields.Many2one(
        "project.project", string="Origin / Governance Project", required=True, ondelete="restrict", index=True, tracking=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    title = fields.Char(required=True, tracking=True)
    category = fields.Selection(
        [
            ("material", "Plastic Material"),
            ("tool_steel", "Tool Steel"),
            ("surface_finish", "Surface Finish"),
            ("runner_gate", "Runner and Gate"),
            ("machine", "Moulding Machine"),
            ("mould_technology", "Mould Technology"),
            ("tolerance_metrology", "Tolerance and Metrology"),
            ("defect_capa", "Defect and CAPA"),
            ("process_trial", "Process and Trial"),
            ("supplier_capability", "Supplier Capability"),
            ("lesson", "Lesson Learned"),
            ("sop_template", "SOP / Checklist / Template"),
        ],
        required=True, index=True, tracking=True,
    )
    version = fields.Char(required=True, default="1.0", tracking=True)
    applicability = fields.Text(required=True)
    controlled_content = fields.Html(required=True, sanitize=True)
    source_standard = fields.Char(required=True, tracking=True)
    source_url = fields.Char(tracking=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", "hjig_knowledge_attachment_rel", "knowledge_id", "attachment_id", string="Source Attachments"
    )
    effective_date = fields.Date(tracking=True)
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    reviewer_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"), ("superseded", "Superseded"), ("obsolete", "Obsolete"), ("rejected", "Rejected")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    supersedes_id = fields.Many2one("hjig.knowledge.item", ondelete="restrict", tracking=True)
    superseded_by_id = fields.Many2one("hjig.knowledge.item", ondelete="restrict", readonly=True, copy=False)
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")

    _code_version_unique = models.Constraint(
        "UNIQUE(code, version)", "Knowledge item code and version must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
            vals["state"] = "draft"
        return super().create(vals_list)

    @api.constrains("reviewer_designation_id", "approver_designation_id", "supersedes_id", "code")
    def _check_governance(self):
        for item in self:
            if item.reviewer_designation_id == item.approver_designation_id:
                raise ValidationError(_("Knowledge reviewer and approver designations must be different."))
            if item.supersedes_id:
                if item.supersedes_id.code != item.code:
                    raise ValidationError(_("A knowledge revision must keep the same controlled code."))
                if item.supersedes_id.state != "approved":
                    raise ValidationError(_("Only an Approved knowledge item can be superseded."))

    def write(self, vals):
        workflow = {"state", "approval_id", "superseded_by_id", "reviewed_by_id", "reviewed_date"}
        if workflow.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Knowledge approval fields may only change through workflow actions."))
        if any(item.state in ("approved", "superseded", "obsolete") for item in self):
            if set(vals) - (workflow if is_workflow_context(self.env) else set()):
                raise ValidationError(_("Approved, Superseded, or Obsolete knowledge is read-only."))
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)

    def action_submit_review(self):
        for item in self:
            if item.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected knowledge can be submitted."))
            previous_state = item.state
            if self.env.user not in item.reviewer_designation_id.holder_ids:
                raise UserError(_("Only a holder of the Knowledge Reviewer designation may submit this item."))
            if not item.effective_date:
                raise ValidationError(_("Effective Date is required before knowledge approval."))
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": item.project_id.id,
                "target_ref": "%s,%s" % (item._name, item.id),
                "approval_type": "engineering",
                "authority_designation_id": item.approver_designation_id.id,
                "requested_by_id": self.env.user.id,
            })
            item.sudo().with_context(**workflow_context()).write({
                "state": "review", "approval_id": approval.id,
                "reviewed_by_id": self.env.user.id, "reviewed_date": fields.Datetime.now(),
            })
            item._log_transition(previous_state, "review", "reviewed_submitted", approval)

    def action_apply_decision(self):
        for item in self:
            item.check_access_rule("read")
            if item.state != "review" or not item.approval_id:
                raise UserError(_("The knowledge item has no approval decision to apply."))
            if item.approval_id.state == "approved":
                if item.supersedes_id:
                    item.supersedes_id.sudo().with_context(**workflow_context()).write({
                        "state": "superseded", "superseded_by_id": item.id,
                    })
                next_state = "approved"
            elif item.approval_id.state == "rejected":
                next_state = "rejected"
            else:
                raise UserError(_("The knowledge approval decision is still pending."))
            item.sudo().with_context(**workflow_context()).write({"state": next_state})
            item._log_transition("review", next_state, item.approval_id.state, item.approval_id)

    def _log_transition(self, from_state, to_state, decision, approval=False):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state, "to_state": to_state, "decision": decision,
            "actor_id": self.env.user.id, "approval_id": approval.id if approval else False,
        })

    def unlink(self):
        if any(item.state != "draft" for item in self):
            raise UserError(_("Submitted knowledge history cannot be deleted."))
        return super().unlink()


class HjigAiAssistanceLog(models.Model):
    _name = "hjig.ai.assistance.log"
    _description = "Hongyi AI Assistance Provenance Log"
    _inherit = ["hjig.target.mixin"]
    _order = "run_date desc, id desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Assistance For")
    capability = fields.Selection(
        [
            ("extract", "Extract / Structure"),
            ("classify", "Classify / Map"),
            ("draft", "Draft"),
            ("validate", "Validate / Gap Check"),
            ("impact", "Impact Analysis"),
            ("retrieve", "Knowledge Retrieval"),
            ("summarise", "Summarise / Explain"),
        ],
        required=True, index=True,
    )
    model_identity = fields.Char(required=True)
    permission_scope = fields.Text(required=True)
    output_summary = fields.Text(required=True)
    knowledge_source_ids = fields.Many2many(
        "hjig.knowledge.item", "hjig_ai_knowledge_rel", "log_id", "knowledge_id", string="Knowledge Sources"
    )
    evidence_source_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_ai_evidence_rel", "log_id", "evidence_id", string="Evidence Sources"
    )
    confidence = fields.Float(required=True)
    warnings = fields.Text()
    authoritative = fields.Boolean(compute="_compute_authoritative", store=True)
    run_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    disposition = fields.Selection(
        [("informational", "Informational"), ("accepted", "Accepted"), ("edited", "Accepted with Edits"), ("rejected", "Rejected")],
        default="informational", required=True, readonly=True,
    )
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_date = fields.Datetime(readonly=True)
    review_notes = fields.Text(readonly=True)

    _code_unique = models.Constraint("UNIQUE(code)", "AI assistance log code must be unique.")

    @api.depends("knowledge_source_ids.state")
    def _compute_authoritative(self):
        for log in self:
            log.authoritative = bool(log.knowledge_source_ids) and all(
                item.state == "approved" for item in log.knowledge_source_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not is_workflow_context(self.env):
            raise UserError(_("AI assistance logs may only be created by the governed AI service."))
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["disposition"] = "informational"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.ai.assistance.log") or _("New")
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id", "confidence", "knowledge_source_ids", "evidence_source_ids")
    def _check_log(self):
        for log in self:
            log._check_target_project(log.target_ref, log.project_id)
            if not 0 <= log.confidence <= 100:
                raise ValidationError(_("AI confidence must be between 0 and 100."))
            if any(evidence.project_id != log.project_id for evidence in log.evidence_source_ids):
                raise ValidationError(_("AI evidence sources must belong to the same project."))
            if any(item.company_id != log.company_id for item in log.knowledge_source_ids):
                raise ValidationError(_("AI knowledge sources must belong to the same company."))

    @api.model
    def _log_assistance(self, values):
        return self.sudo().with_context(**workflow_context()).create(values)

    def _record_disposition(self, disposition, notes=False):
        self.check_access_rights("read")
        for log in self:
            log.check_access_rule("read")
            if log.disposition != "informational":
                raise UserError(_("AI disposition has already been recorded."))
            log.sudo().with_context(**workflow_context()).write({
                "disposition": disposition,
                "reviewed_by_id": self.env.user.id,
                "reviewed_date": fields.Datetime.now(),
                "review_notes": notes or False,
            })

    def action_accept(self):
        self._record_disposition("accepted")

    def action_reject(self):
        self._record_disposition("rejected")

    def write(self, vals):
        allowed = {"disposition", "reviewed_by_id", "reviewed_date", "review_notes"}
        if not is_workflow_context(self.env) or set(vals) - allowed:
            raise UserError(_("AI provenance records are immutable after creation."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("AI provenance records cannot be deleted."))
