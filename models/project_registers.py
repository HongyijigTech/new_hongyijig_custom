# -*- coding: utf-8 -*-
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


CHATTER_FIELDS = {"message_follower_ids", "message_ids", "activity_ids"}


def _valid_evidence_url(value):
    if not value:
        return False
    cleaned = value.strip()
    if any(character.isspace() for character in cleaned):
        return False
    parsed = urlparse(cleaned)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _attachments_belong_to(record, attachments):
    return all(item.res_model == record._name and item.res_id == record.id for item in attachments)


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

    _snapshot_fields = (
        "source_mould_id", "source_part_id", "mould_number", "part_name", "part_number",
        "part_category", "surface_finish", "surface_details", "part_material",
        "standard_shrinkage", "customer_shrinkage", "part_weight_grams", "qps",
        "mould_configuration", "cavitation", "mould_base_steel", "core_steel",
        "cavity_steel", "runner_type", "gate_type",
    )

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

    def _snapshot_values(self, mould, part):
        return {
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
        }

    def _check_snapshot_integrity(self):
        for plan in self:
            plan._check_source_moulds()
            if not plan.source_mould_ids or plan.source_mould_ids.filtered(lambda mould: mould.x_workflow_state != "approved"):
                raise ValidationError(_("Every source Mould Plan must be Approved."))
            expected = {}
            for mould in plan.source_mould_ids:
                for part in mould.x_part_ids:
                    expected[(mould.id, part.id)] = plan._snapshot_values(mould, part)
            actual = {(line.source_mould_id.id, line.source_part_id.id): line for line in plan.line_ids}
            if len(actual) != len(plan.line_ids) or set(actual) != set(expected):
                raise ValidationError(_("Final Plan lines no longer match the selected approved Mould Plans. Regenerate them."))
            for key, line in actual.items():
                values = expected[key]
                changed = any(
                    (line[field].id if field in ("source_mould_id", "source_part_id") else line[field]) != values[field]
                    for field in self._snapshot_fields
                )
                if changed:
                    raise ValidationError(_("Final Plan snapshot data has changed. Regenerate the lines."))

    def write(self, vals):
        controlled = set(self._fields) - CHATTER_FIELDS
        if {"owner_designation_id", "approver_designation_id"}.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only a Project Administrator may change designation authority."))
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.workflow_state in ("approved", "superseded")):
            allowed_supersede = set(vals) == {"workflow_state"} and vals.get("workflow_state") == "superseded"
            if not allowed_supersede or any(
                not rec.approver_designation_id._user_holds_for_project(self.env.user, rec.project_id)
                for rec in self
            ):
                raise ValidationError(_("Approved or superseded Final Mould Plans are read-only."))
        identity_fields = {"project_id", "revision", "source_mould_ids", "owner_designation_id", "approver_designation_id"}
        if identity_fields.intersection(vals) and self.filtered(lambda rec: rec.workflow_state != "draft"):
            raise ValidationError(_("Plan identity, sources and designation authority are locked after submission."))
        if "workflow_state" in vals:
            target = vals["workflow_state"]
            for plan in self:
                if plan.workflow_state == "draft" and target == "review":
                    if set(vals) - {"workflow_state", "submitted_by_id"}:
                        raise ValidationError(_("Save plan changes before using the controlled submission transition."))
                    plan._check_snapshot_integrity()
                    if not plan.owner_designation_id._user_holds_for_project(self.env.user, plan.project_id) or vals.get("submitted_by_id") != self.env.user.id:
                        raise UserError(_("Only the Owner Designation holder may submit this Final Mould Plan."))
                elif plan.workflow_state == "review" and target == "approved":
                    if set(vals) - {"workflow_state", "approved_by_id"}:
                        raise ValidationError(_("Save review changes before using the controlled approval transition."))
                    plan._check_snapshot_integrity()
                    if not plan.approver_designation_id._user_holds_for_project(self.env.user, plan.project_id) or plan.submitted_by_id == self.env.user:
                        raise UserError(_("A different current Approver Designation holder must approve this Final Mould Plan."))
                    if not plan.effective_date or vals.get("approved_by_id") != self.env.user.id:
                        raise ValidationError(_("Effective Date and the authenticated approver are required."))
                elif plan.workflow_state == "approved" and target == "superseded":
                    if set(vals) != {"workflow_state"}:
                        raise ValidationError(_("Superseding may only change workflow status."))
                    if not plan.approver_designation_id._user_holds_for_project(self.env.user, plan.project_id):
                        raise UserError(_("Only the Approver Designation holder may supersede this plan."))
                else:
                    raise ValidationError(_("Invalid Final Mould Plan workflow transition."))
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
                    commands.append((0, 0, plan._snapshot_values(mould, part)))
            plan.line_ids = commands

    def action_submit_review(self):
        for plan in self:
            if plan.workflow_state != "draft" or not plan.line_ids:
                raise ValidationError(_("Generate the Final Plan lines before submission."))
            if not plan.owner_designation_id._user_holds_for_project(self.env.user, plan.project_id):
                raise UserError(_("Only a current holder of the Owner Designation may submit this Final Mould Plan."))
            plan.write({
                "workflow_state": "review", "submitted_by_id": self.env.user.id,
            })

    def action_approve(self):
        for plan in self:
            if plan.workflow_state != "review":
                raise UserError(_("Only a Final Mould Plan Under Review can be approved."))
            if not plan.approver_designation_id._user_holds_for_project(self.env.user, plan.project_id):
                raise UserError(_("Only a current holder of the Approver Designation may approve this Final Mould Plan."))
            if plan.submitted_by_id == self.env.user:
                raise ValidationError(_("The same user cannot submit and approve the Final Mould Plan."))
            if not plan.effective_date:
                raise ValidationError(_("Effective Date is required before approval."))
            previous = self.search([
                ("project_id", "=", plan.project_id.id), ("workflow_state", "=", "approved"), ("id", "!=", plan.id),
            ])
            previous.write({"workflow_state": "superseded"})
            plan.write({
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            plan = self.env["hjig.final.mould.plan"].browse(vals.get("plan_id")).exists()
            mould = self.env["x_mould"].browse(vals.get("source_mould_id")).exists()
            part = self.env["x_mould_part"].browse(vals.get("source_part_id")).exists()
            if not plan or plan.workflow_state != "draft" or mould not in plan.source_mould_ids:
                raise ValidationError(_("Snapshot lines can only come from a selected Draft Final Mould Plan source."))
            if mould.x_workflow_state != "approved" or part.x_mould_id != mould:
                raise ValidationError(_("Snapshot source mould and part must be approved and correctly linked."))
            expected = plan._snapshot_values(mould, part)
            if any(vals.get(field) != expected[field] for field in plan._snapshot_fields):
                raise ValidationError(_("Snapshot values must exactly match their approved source records."))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals).intersection(self.env["hjig.final.mould.plan"]._snapshot_fields):
            raise ValidationError(_("Generated Final Mould Plan snapshot lines cannot be edited."))
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
            risk.escalation_required = risk.risk_score >= 16

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_006")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if vals.get("risk_id", _("New")) == _("New"):
                vals["risk_id"] = self.env["ir.sequence"].next_by_code("hjig.project.risk") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        controlled = set(self._fields) - CHATTER_FIELDS
        if {"owner_designation_id", "approver_designation_id"}.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only a Project Administrator may change designation authority."))
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.status == "resolved"):
            raise ValidationError(_("Resolved risks are read-only and cannot be resolved again."))
        if "status" in vals:
            target = vals["status"]
            for risk in self:
                if risk.status == "open" and target == "mitigating":
                    if set(vals) != {"status"} or not risk.owner_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                        raise UserError(_("Only the Owner Designation holder may start mitigation."))
                elif risk.status in ("open", "mitigating") and target == "accepted":
                    if set(vals) != {"status"} or not risk.approver_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                        raise UserError(_("Only the Approver Designation holder may accept a risk."))
                elif target == "resolved":
                    if set(vals) - {"status", "resolved_by_id", "resolved_date"}:
                        raise ValidationError(_("Save risk changes before using the controlled resolution transition."))
                    if not risk.approver_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                        raise UserError(_("Only a current holder of the Approver Designation may resolve this risk."))
                    notes = vals.get("resolution_notes", risk.resolution_notes)
                    if not notes or vals.get("resolved_by_id") != self.env.user.id or not vals.get("resolved_date"):
                        raise ValidationError(_("Resolution notes and authenticated resolution metadata are required."))
                else:
                    raise ValidationError(_("Invalid Risk workflow transition."))
        return super().write(vals)

    def action_start_mitigation(self):
        self.write({"status": "mitigating"})

    def action_accept(self):
        self.write({"status": "accepted"})

    def action_resolve(self):
        for risk in self:
            if not risk.approver_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                raise UserError(_("Only a current holder of the Approver Designation may resolve this risk."))
            if not risk.resolution_notes:
                raise ValidationError(_("Resolution Notes are required."))
            risk.write({
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

    def _check_closure_requirements(self):
        for issue in self:
            if not issue.root_cause or not issue.closure_notes:
                raise ValidationError(_("Root Cause and Closure Notes are required."))
            if not issue.closure_attachment_ids and not issue.closure_evidence_url:
                raise ValidationError(_("At least one closure evidence attachment or link is required."))
            if issue.closure_evidence_url and not _valid_evidence_url(issue.closure_evidence_url):
                raise ValidationError(_("Closure evidence link must be a valid HTTP or HTTPS URL."))
            if not _attachments_belong_to(issue, issue.closure_attachment_ids):
                raise ValidationError(_("Every closure attachment must belong to this Issue record."))

    def write(self, vals):
        controlled = set(self._fields) - CHATTER_FIELDS
        if {"owner_designation_id", "approver_designation_id"}.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only a Project Administrator may change designation authority."))
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.status == "closed"):
            raise ValidationError(_("Closed issues are read-only and cannot be closed again."))
        if "status" in vals:
            target = vals["status"]
            for issue in self:
                if issue.status == "open" and target == "in_progress":
                    if set(vals) != {"status"} or not issue.owner_designation_id._user_holds_for_project(self.env.user, issue.project_id):
                        raise UserError(_("Only the Owner Designation holder may start issue work."))
                elif issue.status in ("open", "in_progress") and target == "blocked":
                    if set(vals) != {"status"} or not issue.owner_designation_id._user_holds_for_project(self.env.user, issue.project_id):
                        raise UserError(_("Only the Owner Designation holder may mark an issue blocked."))
                elif issue.status == "blocked" and target == "in_progress":
                    if set(vals) != {"status"} or not issue.owner_designation_id._user_holds_for_project(self.env.user, issue.project_id):
                        raise UserError(_("Only the Owner Designation holder may resume issue work."))
                elif target == "closed":
                    if set(vals) - {"status", "closed_by_id", "closed_date"}:
                        raise ValidationError(_("Save issue changes before using the controlled closure transition."))
                    if not issue.approver_designation_id._user_holds_for_project(self.env.user, issue.project_id):
                        raise UserError(_("Only a current holder of the Approver Designation may close this issue."))
                    root_cause = vals.get("root_cause", issue.root_cause)
                    closure_notes = vals.get("closure_notes", issue.closure_notes)
                    if not root_cause or not closure_notes or vals.get("closed_by_id") != self.env.user.id or not vals.get("closed_date"):
                        raise ValidationError(_("Root cause, closure notes and authenticated closure metadata are required."))
                    issue._check_closure_requirements()
                else:
                    raise ValidationError(_("Invalid Issue workflow transition."))
        return super().write(vals)

    def action_start_work(self):
        self.write({"status": "in_progress"})

    def action_block(self):
        self.write({"status": "blocked"})

    def action_resume(self):
        self.write({"status": "in_progress"})

    def action_close(self):
        for issue in self:
            if not issue.approver_designation_id._user_holds_for_project(self.env.user, issue.project_id):
                raise UserError(_("Only a current holder of the Approver Designation may close this issue."))
            issue._check_closure_requirements()
            issue.write({
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
    supplier_cost = fields.Monetary(
        currency_field="currency_id",
        tracking=True,
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )
    supplier_lead_time_days = fields.Integer(tracking=True)
    supplier_approval_status = fields.Selection(
        [("not_required", "Not Required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True, default="pending", tracking=True,
    )
    supplier_approval_evidence_url = fields.Char(
        tracking=True,
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )
    supplier_evidence_ids = fields.Many2many(
        "ir.attachment", "hjig_ecn_supplier_attachment_rel", "ecn_id", "attachment_id",
        string="Supplier Approval Evidence",
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )
    customer_cost = fields.Monetary(
        currency_field="currency_id",
        tracking=True,
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )
    customer_approval_status = fields.Selection(
        [("not_required", "Not Required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True, default="pending", tracking=True,
    )
    customer_approval_evidence_url = fields.Char(
        tracking=True,
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )
    customer_evidence_ids = fields.Many2many(
        "ir.attachment", "hjig_ecn_customer_attachment_rel", "ecn_id", "attachment_id",
        string="Customer Approval Evidence",
        groups="new_hongyijig_custom.group_hjig_commercial_user",
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

    def _check_approval_requirements(self):
        for ecn in self:
            confidential = ecn.sudo()
            for party, status, attachments, url in (
                (
                    _("Supplier"), ecn.supplier_approval_status,
                    confidential.supplier_evidence_ids, confidential.supplier_approval_evidence_url,
                ),
                (
                    _("Customer"), ecn.customer_approval_status,
                    confidential.customer_evidence_ids, confidential.customer_approval_evidence_url,
                ),
            ):
                if status not in ("approved", "not_required"):
                    raise ValidationError(_("%s approval must be Approved or Not Required.") % party)
                if status == "approved" and not attachments and not url:
                    raise ValidationError(_("%s approval evidence is required.") % party)
                if url and not _valid_evidence_url(url):
                    raise ValidationError(_("%s approval evidence link must be a valid HTTP or HTTPS URL.") % party)
                if not _attachments_belong_to(ecn, attachments):
                    raise ValidationError(_("Every %s approval attachment must belong to this ECN.") % party)
            if "not_required" in (ecn.supplier_approval_status, ecn.customer_approval_status) and not ecn.remarks:
                raise ValidationError(_("Remarks must explain every Not Required approval decision."))
            if ecn.customer_approval_status == "approved" and not ecn.customer_approval_date:
                raise ValidationError(_("Customer Approval Date is required."))

    def write(self, vals):
        controlled = set(self._fields) - CHATTER_FIELDS
        authority_fields = {"project_id", "raised_by_designation_id", "owner_designation_id", "approver_designation_id"}
        if authority_fields.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only a Project Administrator may change project or designation authority."))
        if authority_fields.intersection(vals) and self.filtered(lambda rec: rec.status != "draft"):
            raise ValidationError(_("Project and designation authority are locked after ECN submission."))
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.status in ("closed", "rejected")):
            raise ValidationError(_("Closed or rejected ECNs are read-only."))
        for ecn in self.filtered(lambda rec: rec.status == "approved" and "status" not in vals):
            if set(vals) - CHATTER_FIELDS - {"implementation_date", "remarks"}:
                raise ValidationError(_("Approved ECN definition, costs and evidence are locked."))
            if set(vals).intersection({"implementation_date", "remarks"}) and not ecn.owner_designation_id._user_holds_for_project(self.env.user, ecn.project_id):
                raise UserError(_("Only the Owner Designation holder may update implementation details."))
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.status == "implemented" and "status" not in vals):
            raise ValidationError(_("Implemented ECNs are read-only until controlled closure."))
        if "status" in vals:
            target = vals["status"]
            for ecn in self:
                if ecn.status == "draft" and target == "review":
                    if set(vals) - {"status", "submitted_by_id"}:
                        raise ValidationError(_("Save ECN changes before using the controlled submission transition."))
                    if not ecn.owner_designation_id._user_holds_for_project(self.env.user, ecn.project_id) or vals.get("submitted_by_id") != self.env.user.id:
                        raise UserError(_("Only the Owner Designation holder may submit this ECN."))
                    if not ecn.impacted_part_ids and not ecn.impacted_mould_ids:
                        raise ValidationError(_("Select at least one impacted part or mould."))
                elif ecn.status == "review" and target == "approved":
                    if set(vals) - {"status", "approved_by_id"}:
                        raise ValidationError(_("Save review changes before using the controlled approval transition."))
                    if not ecn.approver_designation_id._user_holds_for_project(self.env.user, ecn.project_id) or ecn.submitted_by_id == self.env.user:
                        raise UserError(_("A different current Approver Designation holder must approve this ECN."))
                    if vals.get("approved_by_id") != self.env.user.id:
                        raise ValidationError(_("Authenticated approval metadata is required."))
                    ecn._check_approval_requirements()
                elif ecn.status == "approved" and target == "implemented":
                    if set(vals) != {"status"}:
                        raise ValidationError(_("Implementation transition may only change workflow status."))
                    if not ecn.owner_designation_id._user_holds_for_project(self.env.user, ecn.project_id) or not ecn.implementation_date:
                        raise UserError(_("Only the Owner Designation holder may implement an ECN with an Implementation Date."))
                elif ecn.status == "implemented" and target == "closed":
                    if set(vals) - {"status", "closed_date"}:
                        raise ValidationError(_("Closure transition may only set controlled closure metadata."))
                    if not ecn.approver_designation_id._user_holds_for_project(self.env.user, ecn.project_id) or not vals.get("closed_date"):
                        raise UserError(_("Only the Approver Designation holder may close this ECN."))
                else:
                    raise ValidationError(_("Invalid ECN workflow transition."))
        return super().write(vals)

    def action_submit_review(self):
        for ecn in self:
            if ecn.status != "draft":
                raise UserError(_("Only Draft ECNs can be submitted."))
            if not ecn.owner_designation_id._user_holds_for_project(self.env.user, ecn.project_id):
                raise UserError(_("Only a current holder of the Owner Designation may submit this ECN."))
            if not ecn.impacted_part_ids and not ecn.impacted_mould_ids:
                raise ValidationError(_("Select at least one impacted part or mould."))
            ecn.write({"status": "review", "submitted_by_id": self.env.user.id})

    def action_approve(self):
        for ecn in self:
            if ecn.status != "review":
                raise UserError(_("Only ECNs Under Review can be approved."))
            if not ecn.approver_designation_id._user_holds_for_project(self.env.user, ecn.project_id):
                raise UserError(_("Only a current holder of the Approver Designation may approve this ECN."))
            if ecn.submitted_by_id == self.env.user:
                raise ValidationError(_("The same user cannot submit and approve an ECN."))
            ecn._check_approval_requirements()
            ecn.write({"status": "approved", "approved_by_id": self.env.user.id})

    def action_mark_implemented(self):
        for ecn in self:
            if ecn.status != "approved" or not ecn.implementation_date:
                raise ValidationError(_("Set Implementation Date on an Approved ECN first."))
            if not ecn.owner_designation_id._user_holds_for_project(self.env.user, ecn.project_id):
                raise UserError(_("Only a current holder of the Owner Designation may mark implementation."))
            ecn.write({"status": "implemented"})

    def action_close(self):
        for ecn in self:
            if ecn.status != "implemented":
                raise UserError(_("Only Implemented ECNs can be closed."))
            if not ecn.approver_designation_id._user_holds_for_project(self.env.user, ecn.project_id):
                raise UserError(_("Only a current holder of the Approver Designation may close this ECN."))
            ecn.write({
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
