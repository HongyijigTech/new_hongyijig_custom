# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def _artifact_authority(env, xmlid):
    artifact = env.ref(xmlid, raise_if_not_found=False)
    if not artifact:
        return {}
    return {
        "owner_designation_id": artifact.owner_designation_id.id,
        "approver_designation_id": artifact.approver_designation_id.id,
    }


class HjigFinalMouldPlan(models.Model):
    _name = "hjig.final.mould.plan"
    _description = "Final Mould Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "plan_number"
    _order = "project_id, revision desc, id desc"

    plan_number = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    project_code = fields.Char(related="project_id.x_project_code", store=True, readonly=True)
    revision = fields.Char(required=True, default="R00", tracking=True)
    source_mould_ids = fields.Many2many(
        "x_mould", "hjig_final_plan_mould_rel", "plan_id", "mould_id",
        string="Approved Source Mould Plans", required=True, tracking=True,
    )
    line_ids = fields.One2many("hjig.final.mould.plan.line", "plan_id", string="Final Plan Lines")
    line_count = fields.Integer(compute="_compute_line_count")
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    effective_date = fields.Date(tracking=True)
    workflow_state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"), ("superseded", "Superseded")],
        required=True, default="draft", copy=False, index=True, tracking=True,
    )
    notes = fields.Text()

    _project_revision_unique = models.Constraint(
        "UNIQUE(project_id, revision)", "Final Mould Plan revision must be unique within the project."
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for plan in self:
            plan.line_count = len(plan.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_007")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if vals.get("plan_number", _("New")) == _("New"):
                vals["plan_number"] = self.env["ir.sequence"].next_by_code("hjig.final.mould.plan") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        locked = set(self._fields) - {"message_follower_ids", "message_ids", "activity_ids"}
        if locked.intersection(vals) and self.filtered(lambda rec: rec.workflow_state in ("approved", "superseded")):
            if not self.env.context.get("allow_final_plan_workflow"):
                raise ValidationError(_("Approved or superseded Final Mould Plans are read-only."))
        if "workflow_state" in vals and not self.env.context.get("allow_final_plan_workflow"):
            raise ValidationError(_("Use the controlled workflow buttons to change Final Mould Plan status."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.workflow_state != "draft"):
            raise UserError(_("Only Draft Final Mould Plans may be deleted."))
        return super().unlink()

    @api.constrains("source_mould_ids", "project_id")
    def _check_source_moulds(self):
        for plan in self:
            if plan.source_mould_ids.filtered(lambda mould: mould.x_project_id != plan.project_id):
                raise ValidationError(_("All source mould plans must belong to the same project."))

    def action_generate_lines(self):
        for plan in self:
            if plan.workflow_state != "draft":
                raise UserError(_("Final Plan lines can only be generated while Draft."))
            if not plan.source_mould_ids:
                raise ValidationError(_("Select at least one approved source Mould Plan."))
            unapproved = plan.source_mould_ids.filtered(lambda mould: mould.x_workflow_state != "approved")
            if unapproved:
                raise ValidationError(_("Every source Mould Plan must be Approved before the Final Plan is generated."))
            commands = [(5, 0, 0)]
            for mould in plan.source_mould_ids.sorted(lambda item: (item.x_mould_number or "", item.id)):
                for part in mould.x_part_ids.sorted(lambda item: (item.x_part_number or "", item.id)):
                    commands.append((0, 0, {
                        "source_mould_id": mould.id,
                        "source_part_id": part.id,
                        "mould_number": mould.x_mould_number,
                        "part_name": part.x_name,
                        "part_number": part.x_part_number,
                        "part_category": dict(part._fields["x_part_category"].selection).get(part.x_part_category),
                        "surface_finish": part.x_surface_grade_code,
                        "surface_details": part.x_surface_details,
                        "part_material": part.x_part_material,
                        "standard_shrinkage": part.x_standard_shrinkage,
                        "customer_shrinkage": part.x_customer_shrinkage,
                        "part_weight_grams": part.x_part_weight_grams,
                        "qps": part.x_qps,
                        "mould_configuration": dict(part._fields["x_mould_configuration"].selection).get(part.x_mould_configuration),
                        "cavitation": part.x_cavitation,
                        "mould_base_steel": part.x_mould_base_steel_id.display_name or part.x_mould_base_steel_grade,
                        "core_steel": part.x_core_steel_id.display_name or " - ".join(filter(None, [part.x_core_steel_brand, part.x_core_steel_grade])),
                        "cavity_steel": part.x_cavity_steel_id.display_name or " - ".join(filter(None, [part.x_cavity_steel_brand, part.x_cavity_steel_grade])),
                        "runner_type": dict(part._fields["x_runner_type"].selection).get(part.x_runner_type),
                        "gate_type": part.x_gate_type,
                    }))
            plan.line_ids = commands

    def action_submit_review(self):
        for plan in self:
            if plan.workflow_state != "draft" or not plan.line_ids:
                raise ValidationError(_("Generate the Final Plan lines before submission."))
            if self.env.user not in plan.owner_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Owner Designation may submit this Final Mould Plan."))
            plan.with_context(allow_final_plan_workflow=True).write({
                "workflow_state": "review", "submitted_by_id": self.env.user.id,
            })

    def action_approve(self):
        for plan in self:
            if plan.workflow_state != "review":
                raise UserError(_("Only a Final Mould Plan Under Review can be approved."))
            if self.env.user not in plan.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may approve this Final Mould Plan."))
            if plan.submitted_by_id == self.env.user:
                raise ValidationError(_("The same user cannot submit and approve the Final Mould Plan."))
            if not plan.effective_date:
                raise ValidationError(_("Effective Date is required before approval."))
            previous = self.search([
                ("project_id", "=", plan.project_id.id), ("workflow_state", "=", "approved"), ("id", "!=", plan.id),
            ])
            previous.with_context(allow_final_plan_workflow=True).write({"workflow_state": "superseded"})
            plan.with_context(allow_final_plan_workflow=True).write({
                "workflow_state": "approved", "approved_by_id": self.env.user.id,
            })


class HjigFinalMouldPlanLine(models.Model):
    _name = "hjig.final.mould.plan.line"
    _description = "Final Mould Plan Snapshot Line"
    _order = "plan_id, mould_number, part_number, id"

    plan_id = fields.Many2one("hjig.final.mould.plan", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="plan_id.project_id", store=True, index=True)
    source_mould_id = fields.Many2one("x_mould", required=True, ondelete="restrict")
    source_part_id = fields.Many2one("x_mould_part", required=True, ondelete="restrict")
    mould_number = fields.Char(required=True, readonly=True)
    part_name = fields.Char(required=True, readonly=True)
    part_number = fields.Char(required=True, readonly=True)
    part_category = fields.Char(readonly=True)
    surface_finish = fields.Char(readonly=True)
    surface_details = fields.Text(readonly=True)
    part_material = fields.Char(readonly=True)
    standard_shrinkage = fields.Char(readonly=True)
    customer_shrinkage = fields.Float(readonly=True)
    part_weight_grams = fields.Float(readonly=True)
    qps = fields.Integer(readonly=True)
    mould_configuration = fields.Char(readonly=True)
    cavitation = fields.Char(readonly=True)
    mould_base_steel = fields.Char(readonly=True)
    core_steel = fields.Char(readonly=True)
    cavity_steel = fields.Char(readonly=True)
    runner_type = fields.Char(readonly=True)
    gate_type = fields.Char(readonly=True)

    def write(self, vals):
        if self.filtered(lambda line: line.plan_id.workflow_state != "draft"):
            raise ValidationError(_("Final Mould Plan snapshot lines are read-only after submission."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.plan_id.workflow_state != "draft"):
            raise UserError(_("Final Mould Plan snapshot lines cannot be deleted after submission."))
        return super().unlink()


class HjigProjectRisk(models.Model):
    _name = "hjig.project.risk"
    _description = "Project Risk Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "risk_id"
    _order = "project_id, risk_score desc, target_date, id"

    risk_id = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    description = fields.Text(required=True, tracking=True)
    category = fields.Selection(
        [("technical", "Technical"), ("quality", "Quality"), ("resource", "Resource"),
         ("schedule", "Schedule"), ("commercial", "Commercial"), ("supplier", "Supplier"),
         ("customer", "Customer"), ("other", "Other")], required=True, tracking=True,
    )
    probability = fields.Selection(
        [("1", "1 - Rare (<10%)"), ("2", "2 - Unlikely (10-30%)"), ("3", "3 - Possible (30-50%)"),
         ("4", "4 - Likely (50-70%)"), ("5", "5 - Almost Certain (>70%)")], required=True, tracking=True,
    )
    impact = fields.Selection(
        [("1", "1 - Insignificant"), ("2", "2 - Minor (3-7 days delay)"),
         ("3", "3 - Moderate"), ("4", "4 - Major (Trial delay / Cost impact)"),
         ("5", "5 - Severe / Launch impact")], required=True, tracking=True,
    )
    risk_score = fields.Integer(compute="_compute_risk_score", store=True, index=True)
    escalation_required = fields.Boolean(compute="_compute_risk_score", store=True, index=True)
    mitigation_plan = fields.Text(required=True, tracking=True)
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    target_date = fields.Date(required=True, tracking=True)
    next_review_date = fields.Date(required=True, tracking=True)
    status = fields.Selection(
        [("open", "Open"), ("mitigating", "Mitigating"), ("accepted", "Accepted"), ("resolved", "Resolved")],
        required=True, default="open", tracking=True,
    )
    resolution_notes = fields.Text(tracking=True)
    resolved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    resolved_date = fields.Date(readonly=True, copy=False, tracking=True)

    _project_risk_id_unique = models.Constraint("UNIQUE(project_id, risk_id)", "Risk ID must be unique within the project.")

    @api.depends("probability", "impact")
    def _compute_risk_score(self):
        for risk in self:
            risk.risk_score = int(risk.probability or 0) * int(risk.impact or 0)
            risk.escalation_required = risk.risk_score >= 15

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_006")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if vals.get("risk_id", _("New")) == _("New"):
                vals["risk_id"] = self.env["ir.sequence"].next_by_code("hjig.project.risk") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda rec: rec.status == "resolved") and not self.env.context.get("allow_risk_resolution"):
            controlled = set(self._fields) - {"message_follower_ids", "message_ids", "activity_ids"}
            if controlled.intersection(vals):
                raise ValidationError(_("Resolved risks are read-only."))
        if vals.get("status") == "resolved" and not self.env.context.get("allow_risk_resolution"):
            raise ValidationError(_("Use the Resolve Risk button."))
        return super().write(vals)

    def action_resolve(self):
        for risk in self:
            if self.env.user not in risk.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may resolve this risk."))
            if not risk.resolution_notes:
                raise ValidationError(_("Resolution Notes are required."))
            risk.with_context(allow_risk_resolution=True).write({
                "status": "resolved", "resolved_by_id": self.env.user.id,
                "resolved_date": fields.Date.context_today(risk),
            })


class HjigProjectIssue(models.Model):
    _name = "hjig.project.issue"
    _description = "Project Issue Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "issue_id"
    _order = "project_id, priority desc, target_closure_date, id"

    issue_id = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    description = fields.Text(required=True, tracking=True)
    category = fields.Selection(
        [("technical", "Technical"), ("quality", "Quality"), ("schedule", "Schedule"),
         ("commercial", "Commercial"), ("supplier", "Supplier"), ("customer", "Customer"),
         ("other", "Other")], required=True, tracking=True,
    )
    priority = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        required=True, default="medium", tracking=True,
    )
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    date_raised = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    status = fields.Selection(
        [("open", "Open"), ("in_progress", "In Progress"), ("blocked", "Blocked"), ("closed", "Closed")],
        required=True, default="open", tracking=True,
    )
    aging_days = fields.Integer(compute="_compute_aging_days")
    root_cause = fields.Text(tracking=True)
    next_review_date = fields.Date(required=True, tracking=True)
    target_closure_date = fields.Date(required=True, tracking=True)
    closure_notes = fields.Text(tracking=True)
    closure_evidence_url = fields.Char(tracking=True)
    closure_attachment_ids = fields.Many2many("ir.attachment", string="Closure Evidence Attachments")
    closed_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    closed_date = fields.Date(readonly=True, copy=False, tracking=True)

    _project_issue_id_unique = models.Constraint("UNIQUE(project_id, issue_id)", "Issue ID must be unique within the project.")

    @api.depends("date_raised", "closed_date")
    def _compute_aging_days(self):
        today = fields.Date.context_today(self)
        for issue in self:
            end = issue.closed_date or today
            issue.aging_days = max((end - issue.date_raised).days, 0) if issue.date_raised else 0

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_009")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if vals.get("issue_id", _("New")) == _("New"):
                vals["issue_id"] = self.env["ir.sequence"].next_by_code("hjig.project.issue") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda rec: rec.status == "closed") and not self.env.context.get("allow_issue_closure"):
            controlled = set(self._fields) - {"message_follower_ids", "message_ids", "activity_ids"}
            if controlled.intersection(vals):
                raise ValidationError(_("Closed issues are read-only."))
        if vals.get("status") == "closed" and not self.env.context.get("allow_issue_closure"):
            raise ValidationError(_("Use the Close Issue button."))
        return super().write(vals)

    def action_close(self):
        for issue in self:
            if self.env.user not in issue.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may close this issue."))
            if not issue.root_cause or not issue.closure_notes:
                raise ValidationError(_("Root Cause and Closure Notes are required."))
            if not issue.closure_attachment_ids and not issue.closure_evidence_url:
                raise ValidationError(_("At least one closure evidence attachment or link is required."))
            issue.with_context(allow_issue_closure=True).write({
                "status": "closed", "closed_by_id": self.env.user.id,
                "closed_date": fields.Date.context_today(issue),
            })


class HjigProjectEcn(models.Model):
    _name = "hjig.project.ecn"
    _description = "Engineering Change Notice Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "ecn_id"
    _order = "project_id, raised_date desc, id desc"

    ecn_id = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    description = fields.Text(required=True, tracking=True)
    component_name = fields.Char(required=True, tracking=True)
    impacted_part_ids = fields.Many2many("x_mould_part", string="Impacted Parts", tracking=True)
    impacted_mould_ids = fields.Many2many("x_mould", string="Impacted Tools / Moulds", tracking=True)
    change_reason = fields.Text(required=True, tracking=True)
    raised_by_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    raised_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    currency_id = fields.Many2one(related="project_id.company_id.currency_id", store=True, readonly=True)
    supplier_cost = fields.Monetary(currency_field="currency_id", tracking=True)
    supplier_lead_time_days = fields.Integer(tracking=True)
    supplier_approval_status = fields.Selection(
        [("not_required", "Not Required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True, default="pending", tracking=True,
    )
    supplier_approval_evidence_url = fields.Char(tracking=True)
    supplier_evidence_ids = fields.Many2many(
        "ir.attachment", "hjig_ecn_supplier_attachment_rel", "ecn_id", "attachment_id",
        string="Supplier Approval Evidence",
    )
    customer_cost = fields.Monetary(currency_field="currency_id", tracking=True)
    customer_approval_status = fields.Selection(
        [("not_required", "Not Required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True, default="pending", tracking=True,
    )
    customer_approval_evidence_url = fields.Char(tracking=True)
    customer_evidence_ids = fields.Many2many(
        "ir.attachment", "hjig_ecn_customer_attachment_rel", "ecn_id", "attachment_id",
        string="Customer Approval Evidence",
    )
    customer_approval_date = fields.Date(tracking=True)
    status = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"),
         ("implemented", "Implemented"), ("closed", "Closed"), ("rejected", "Rejected")],
        required=True, default="draft", copy=False, tracking=True,
    )
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    implementation_date = fields.Date(tracking=True)
    closed_date = fields.Date(readonly=True, copy=False, tracking=True)
    remarks = fields.Text(tracking=True)

    _project_ecn_id_unique = models.Constraint("UNIQUE(project_id, ecn_id)", "ECN ID must be unique within the project.")

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_010")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            vals.setdefault("raised_by_designation_id", vals.get("owner_designation_id") or authority.get("owner_designation_id"))
            if vals.get("ecn_id", _("New")) == _("New"):
                vals["ecn_id"] = self.env["ir.sequence"].next_by_code("hjig.project.ecn") or _("New")
        return super().create(vals_list)

    @api.constrains("impacted_part_ids", "impacted_mould_ids", "project_id")
    def _check_impacted_records(self):
        for ecn in self:
            if ecn.impacted_part_ids.filtered(lambda part: part.x_project_id != ecn.project_id):
                raise ValidationError(_("All impacted parts must belong to the ECN project."))
            if ecn.impacted_mould_ids.filtered(lambda mould: mould.x_project_id != ecn.project_id):
                raise ValidationError(_("All impacted moulds must belong to the ECN project."))

    @api.constrains("supplier_cost", "customer_cost", "supplier_lead_time_days")
    def _check_non_negative_values(self):
        for ecn in self:
            if ecn.supplier_cost < 0 or ecn.customer_cost < 0 or ecn.supplier_lead_time_days < 0:
                raise ValidationError(_("ECN costs and lead-time impact cannot be negative."))

    def write(self, vals):
        if self.filtered(lambda rec: rec.status in ("closed", "rejected")) and not self.env.context.get("allow_ecn_workflow"):
            controlled = set(self._fields) - {"message_follower_ids", "message_ids", "activity_ids"}
            if controlled.intersection(vals):
                raise ValidationError(_("Closed or rejected ECNs are read-only."))
        if "status" in vals and not self.env.context.get("allow_ecn_workflow"):
            raise ValidationError(_("Use the controlled ECN workflow buttons."))
        return super().write(vals)

    def action_submit_review(self):
        for ecn in self:
            if ecn.status != "draft":
                raise UserError(_("Only Draft ECNs can be submitted."))
            if self.env.user not in ecn.owner_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Owner Designation may submit this ECN."))
            if not ecn.impacted_part_ids and not ecn.impacted_mould_ids:
                raise ValidationError(_("Select at least one impacted part or mould."))
            ecn.with_context(allow_ecn_workflow=True).write({"status": "review", "submitted_by_id": self.env.user.id})

    def action_approve(self):
        for ecn in self:
            if ecn.status != "review":
                raise UserError(_("Only ECNs Under Review can be approved."))
            if self.env.user not in ecn.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may approve this ECN."))
            if ecn.submitted_by_id == self.env.user:
                raise ValidationError(_("The same user cannot submit and approve an ECN."))
            for party, status, attachments, url in (
                (_("Supplier"), ecn.supplier_approval_status, ecn.supplier_evidence_ids, ecn.supplier_approval_evidence_url),
                (_("Customer"), ecn.customer_approval_status, ecn.customer_evidence_ids, ecn.customer_approval_evidence_url),
            ):
                if status not in ("approved", "not_required"):
                    raise ValidationError(_("%s approval must be Approved or Not Required.") % party)
                if status == "approved" and not attachments and not url:
                    raise ValidationError(_("%s approval evidence is required.") % party)
            if ecn.customer_approval_status == "approved" and not ecn.customer_approval_date:
                raise ValidationError(_("Customer Approval Date is required."))
            ecn.with_context(allow_ecn_workflow=True).write({"status": "approved", "approved_by_id": self.env.user.id})

    def action_mark_implemented(self):
        for ecn in self:
            if ecn.status != "approved" or not ecn.implementation_date:
                raise ValidationError(_("Set Implementation Date on an Approved ECN first."))
            if self.env.user not in ecn.owner_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Owner Designation may mark implementation."))
            ecn.with_context(allow_ecn_workflow=True).write({"status": "implemented"})

    def action_close(self):
        for ecn in self:
            if ecn.status != "implemented":
                raise UserError(_("Only Implemented ECNs can be closed."))
            if self.env.user not in ecn.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may close this ECN."))
            ecn.with_context(allow_ecn_workflow=True).write({
                "status": "closed", "closed_date": fields.Date.context_today(ecn),
            })


class ProjectProjectRegisters(models.Model):
    _inherit = "project.project"

    hjig_final_mould_plan_count = fields.Integer(compute="_compute_hjig_register_counts")
    hjig_risk_count = fields.Integer(compute="_compute_hjig_register_counts")
    hjig_issue_count = fields.Integer(compute="_compute_hjig_register_counts")
    hjig_ecn_count = fields.Integer(compute="_compute_hjig_register_counts")

    def _compute_hjig_register_counts(self):
        for project in self:
            project.hjig_final_mould_plan_count = self.env["hjig.final.mould.plan"].search_count([("project_id", "=", project.id)])
            project.hjig_risk_count = self.env["hjig.project.risk"].search_count([("project_id", "=", project.id)])
            project.hjig_issue_count = self.env["hjig.project.issue"].search_count([("project_id", "=", project.id)])
            project.hjig_ecn_count = self.env["hjig.project.ecn"].search_count([("project_id", "=", project.id)])

    def _open_hjig_register(self, xmlid):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        action.update({"domain": [("project_id", "=", self.id)], "context": {"default_project_id": self.id}})
        return action

    def action_open_hjig_final_mould_plans(self):
        return self._open_hjig_register("new_hongyijig_custom.action_hjig_final_mould_plan")

    def action_open_hjig_risks(self):
        return self._open_hjig_register("new_hongyijig_custom.action_hjig_project_risk")

    def action_open_hjig_issues(self):
        return self._open_hjig_register("new_hongyijig_custom.action_hjig_project_issue")

    def action_open_hjig_ecns(self):
        return self._open_hjig_register("new_hongyijig_custom.action_hjig_project_ecn")
