# -*- coding: utf-8 -*-
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import (
    record_staging_demo_transition,
    staging_self_approval_demo_enabled,
)


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
        "cavity_steel", "runner_type", "gate_type", "part_picture",
        "dimension_x_mm", "dimension_y_mm", "dimension_z_mm",
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
    readiness_percent = fields.Float(compute="_compute_readiness")
    missing_requirements = fields.Text(compute="_compute_readiness")
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

    @api.depends("project_id", "revision", "source_mould_ids", "line_ids", "effective_date")
    def _compute_readiness(self):
        for plan in self:
            missing = []
            if not plan.project_id:
                missing.append(_("Project"))
            if not plan.revision:
                missing.append(_("Revision"))
            if not plan.source_mould_ids:
                missing.append(_("At least one Approved and Final-Locked Mould Plan"))
            elif plan.source_mould_ids.filtered(
                lambda mould: mould.x_workflow_state != "approved"
                or mould.x_mould_planning_status != "final_locked"
            ):
                missing.append(_("Every source Mould Plan must be Approved and Final-Locked"))
            expected_lines = sum(len(mould.x_part_ids) for mould in plan.source_mould_ids)
            if not plan.line_ids or len(plan.line_ids) != expected_lines:
                missing.append(_("Generate the frozen component snapshot"))
            if not plan.effective_date:
                missing.append(_("Effective Date"))
            plan.missing_requirements = "\n".join(missing)
            plan.readiness_percent = 100.0 * (5 - len(missing)) / 5

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_007")
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if vals.get("plan_number", _("New")) == _("New"):
                vals["plan_number"] = self.env["ir.sequence"].next_by_code("hjig.final.mould.plan") or _("New")
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_007")
        for field_name, designation_id in authority.items():
            if field_name in fields_list and designation_id:
                values[field_name] = designation_id
        return values

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
            # Configuration and total cavitation are mould-level governed
            # decisions.  The former part-level columns are legacy inputs and
            # may be blank, so freezing them would produce an incomplete or
            # misleading Final Mould Plan.
            "mould_configuration": dict(mould._fields["x_mould_configuration"].selection).get(
                mould.x_mould_configuration
            ) or False,
            "cavitation": mould.x_cavitation or False,
            "mould_base_steel": part.x_mould_base_steel_id.display_name or part.x_mould_base_steel_grade,
            "core_steel": part.x_core_steel_id.display_name or " - ".join(filter(None, [part.x_core_steel_brand, part.x_core_steel_grade])),
            "cavity_steel": part.x_cavity_steel_id.display_name or " - ".join(filter(None, [part.x_cavity_steel_brand, part.x_cavity_steel_grade])),
            "runner_type": dict(part._fields["x_runner_type"].selection).get(part.x_runner_type),
            "gate_type": part.x_gate_type,
            "part_picture": part.x_part_picture,
            "dimension_x_mm": part.x_dimension_x_mm,
            "dimension_y_mm": part.x_dimension_y_mm,
            "dimension_z_mm": part.x_dimension_z_mm,
        }

    def _check_snapshot_integrity(self):
        for plan in self:
            plan._check_source_moulds()
            # Snapshot comparison is a server-side governance check.  Read both
            # sides with the same access context so attachment-backed photos do
            # not appear different merely because the submitter cannot directly
            # read an ``ir.attachment`` row belonging to the snapshot line.
            controlled_plan = plan.sudo()
            if not controlled_plan.source_mould_ids or controlled_plan.source_mould_ids.filtered(
                lambda mould: mould.x_workflow_state != "approved"
                or mould.x_mould_planning_status != "final_locked"
            ):
                raise ValidationError(_("Every source Mould Plan must be Approved and Final-Locked."))
            expected = {}
            for mould in controlled_plan.source_mould_ids:
                for part in mould.x_part_ids:
                    expected[(mould.id, part.id)] = controlled_plan._snapshot_values(mould, part)
            actual = {
                (line.source_mould_id.id, line.source_part_id.id): line
                for line in controlled_plan.line_ids
            }
            if len(actual) != len(controlled_plan.line_ids) or set(actual) != set(expected):
                raise ValidationError(_("Final Plan lines no longer match the selected approved Mould Plans. Regenerate them."))
            for key, line in actual.items():
                values = expected[key]
                changed = [
                    field for field in self._snapshot_fields
                    if (line[field].id if field in ("source_mould_id", "source_part_id") else line[field]) != values[field]
                ]
                if changed:
                    labels = ", ".join(line._fields[field].string for field in changed)
                    raise ValidationError(
                        _("Final Plan snapshot data has changed (%s). Regenerate the lines.") % labels
                    )

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
                    same_user_demo = (
                        plan.submitted_by_id == self.env.user
                        and staging_self_approval_demo_enabled(self.env)
                    )
                    if (
                        not plan.approver_designation_id._user_holds_for_project(self.env.user, plan.project_id)
                        or (plan.submitted_by_id == self.env.user and not same_user_demo)
                    ):
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
            unapproved = plan.source_mould_ids.filtered(
                lambda mould: mould.x_workflow_state != "approved"
                or mould.x_mould_planning_status != "final_locked"
            )
            if unapproved:
                raise ValidationError(_("Every source Mould Plan must be Approved and Final-Locked before the Final Plan is generated."))
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
            same_user_demo = (
                plan.submitted_by_id == self.env.user
                and staging_self_approval_demo_enabled(self.env)
            )
            if plan.submitted_by_id == self.env.user and not same_user_demo:
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
            if same_user_demo:
                record_staging_demo_transition(
                    plan, "review", "approved", "staging_demo_approved"
                )


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
    part_picture = fields.Binary(string="Part Photo", readonly=True, attachment=True)
    dimension_x_mm = fields.Float(string="Part Length X (mm)", readonly=True)
    dimension_y_mm = fields.Float(string="Part Width Y (mm)", readonly=True)
    dimension_z_mm = fields.Float(string="Part Height Z (mm)", readonly=True)

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
    origin_requirement_id = fields.Many2one(
        "hjig.programme.run.artifact", string="Raised From Gate Requirement",
        readonly=True, copy=False, ondelete="set null", index=True,
    )
    origin_stage_id = fields.Many2one(
        "hjig.launchguard.stage", string="First Identified At", readonly=True, copy=False, index=True,
    )
    source_type = fields.Selection(
        [("sor", "SOR Review"), ("bop", "BOP Review"), ("mould_plan", "Mould Planning"),
         ("design", "Design Challenge / Assumption"), ("customer", "Customer Input"),
         ("supplier", "Supplier Input"), ("gate_review", "Gate Review"), ("other", "Other")],
        required=True, default="gate_review", tracking=True,
    )
    source_reference = fields.Char(
        required=True, default="Manual gate review", tracking=True,
        help="Exact clause, document revision, part/BOP, email, meeting note, or gate checkpoint that exposed this risk.",
    )
    source_evidence_url = fields.Char(string="Source Evidence Link", tracking=True)
    source_attachment_ids = fields.Many2many(
        "ir.attachment", "hjig_project_risk_source_attachment_rel", "risk_id", "attachment_id",
        string="Source Evidence Attachments",
    )
    cause = fields.Text(tracking=True)
    description = fields.Text(required=True, tracking=True)
    impact_statement = fields.Text(tracking=True)
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
    risk_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        compute="_compute_risk_score", store=True, index=True,
    )
    escalation_required = fields.Boolean(compute="_compute_risk_score", store=True, index=True)
    mitigation_plan = fields.Text(required=True, tracking=True)
    preventive_action = fields.Text(tracking=True)
    contingency_plan = fields.Text(tracking=True)
    trigger_indicator = fields.Text(string="Early Warning / Trigger", tracking=True)
    residual_probability = fields.Selection(
        [("1", "1 - Rare (<10%)"), ("2", "2 - Unlikely (10-30%)"),
         ("3", "3 - Possible (30-50%)"), ("4", "4 - Likely (50-70%)"),
         ("5", "5 - Almost Certain (>70%)")], tracking=True,
    )
    residual_impact = fields.Selection(
        [("1", "1 - Insignificant"), ("2", "2 - Minor"), ("3", "3 - Moderate"),
         ("4", "4 - Major"), ("5", "5 - Severe / Launch impact")], tracking=True,
    )
    residual_score = fields.Integer(compute="_compute_risk_score", store=True, index=True)
    residual_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        compute="_compute_risk_score", store=True, index=True,
    )
    gate_blocker = fields.Boolean(compute="_compute_risk_score", store=True, index=True)
    readiness_percent = fields.Integer(compute="_compute_readiness", store=True, index=True)
    owner_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    approver_designation_id = fields.Many2one("hjig.governance.designation", required=True, ondelete="restrict", tracking=True)
    target_date = fields.Date(required=True, tracking=True)
    next_review_date = fields.Date(required=True, tracking=True)
    status = fields.Selection(
        [("open", "Open"), ("mitigating", "Mitigating"), ("accepted", "Accepted"), ("resolved", "Resolved")],
        required=True, default="open", tracking=True,
    )
    resolution_notes = fields.Text(tracking=True)
    acceptance_basis = fields.Text(tracking=True)
    acceptance_evidence_url = fields.Char(tracking=True)
    acceptance_attachment_ids = fields.Many2many(
        "ir.attachment", "hjig_project_risk_acceptance_attachment_rel", "risk_id", "attachment_id",
        string="Acceptance / Closure Evidence",
    )
    accepted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    accepted_date = fields.Date(readonly=True, copy=False, tracking=True)
    resolved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    resolved_date = fields.Date(readonly=True, copy=False, tracking=True)

    _project_risk_id_unique = models.Constraint("UNIQUE(project_id, risk_id)", "Risk ID must be unique within the project.")

    @staticmethod
    def _score_level(score):
        if score >= 20:
            return "critical"
        if score >= 12:
            return "high"
        if score >= 6:
            return "medium"
        return "low" if score else False

    @api.depends("probability", "impact", "residual_probability", "residual_impact", "status")
    def _compute_risk_score(self):
        for risk in self:
            risk.risk_score = int(risk.probability or 0) * int(risk.impact or 0)
            risk.risk_level = self._score_level(risk.risk_score)
            risk.residual_score = int(risk.residual_probability or 0) * int(risk.residual_impact or 0)
            risk.residual_level = self._score_level(risk.residual_score)
            risk.escalation_required = risk.risk_score >= 16
            risk.gate_blocker = risk.status not in ("accepted", "resolved") and (
                risk.risk_score >= 16 or risk.residual_score >= 16
            )

    @api.depends(
        "source_reference", "cause", "description", "impact_statement", "mitigation_plan",
        "preventive_action", "contingency_plan", "trigger_indicator", "residual_probability",
        "residual_impact", "owner_designation_id", "target_date", "next_review_date",
    )
    def _compute_readiness(self):
        for risk in self:
            checks = [
                bool(risk.source_reference), bool(risk.cause), bool(risk.description),
                bool(risk.impact_statement), bool(risk.mitigation_plan or risk.preventive_action),
                bool(risk.contingency_plan), bool(risk.trigger_indicator),
                bool(risk.residual_probability and risk.residual_impact),
                bool(risk.owner_designation_id), bool(risk.target_date and risk.next_review_date),
            ]
            risk.readiness_percent = round(sum(checks) * 100 / len(checks))

    @api.model_create_multi
    def create(self, vals_list):
        authority = _artifact_authority(self.env, "new_hongyijig_custom.artifact_frm_006")
        requirement = self.env["hjig.programme.run.artifact"].browse(
            self.env.context.get("hjig_programme_artifact_requirement_id")
        ).exists()
        for vals in vals_list:
            vals.update({key: vals.get(key) or value for key, value in authority.items()})
            if requirement and requirement.artifact_code == "FRM-006":
                vals.setdefault("origin_requirement_id", requirement.id)
                vals.setdefault("origin_stage_id", requirement.stage_id.id)
            if vals.get("risk_id", _("New")) == _("New"):
                vals["risk_id"] = self.env["ir.sequence"].next_by_code("hjig.project.risk") or _("New")
        records = super().create(vals_list)
        records._refresh_programme_risk_requirements()
        return records

    def _refresh_programme_risk_requirements(self):
        requirements = self.env["hjig.programme.run.artifact"].search([
            ("project_id", "in", self.mapped("project_id").ids),
            ("artifact_code", "=", "FRM-006"),
        ])
        if requirements:
            open_requirements = requirements.filtered(lambda item: item.run_gate_id.state != "approved")
            if open_requirements.filtered("risk_reviewed"):
                open_requirements.with_context(hjig_risk_review_workflow=True).write({
                    "risk_reviewed": False,
                    "risk_reviewed_by_id": False,
                    "risk_reviewed_on": False,
                })
            requirements._compute_risk_checkpoint()
            requirements._compute_status()

    def _check_operational_readiness(self):
        for risk in self:
            missing = []
            for field_name, label in (
                ("source_reference", _("source reference")), ("cause", _("cause")),
                ("impact_statement", _("impact statement")), ("contingency_plan", _("contingency plan")),
                ("trigger_indicator", _("early-warning trigger")),
                ("residual_probability", _("residual probability")),
                ("residual_impact", _("residual impact")),
            ):
                if not risk[field_name]:
                    missing.append(label)
            if missing:
                raise ValidationError(_("Complete the risk control card before workflow action: %s.") % ", ".join(missing))
            if risk.source_evidence_url and not _valid_evidence_url(risk.source_evidence_url):
                raise ValidationError(_("Source evidence link must be a valid HTTP or HTTPS URL."))
            if not _attachments_belong_to(risk, risk.source_attachment_ids):
                raise ValidationError(_("Every source attachment must belong to this Risk record."))

    def _check_acceptance_evidence(self):
        for risk in self:
            if not risk.acceptance_basis:
                raise ValidationError(_("Acceptance / closure basis is required."))
            if not risk.acceptance_attachment_ids and not risk.acceptance_evidence_url:
                raise ValidationError(_("Add at least one acceptance / closure evidence attachment or link."))
            if risk.acceptance_evidence_url and not _valid_evidence_url(risk.acceptance_evidence_url):
                raise ValidationError(_("Acceptance evidence link must be a valid HTTP or HTTPS URL."))
            if not _attachments_belong_to(risk, risk.acceptance_attachment_ids):
                raise ValidationError(_("Every acceptance attachment must belong to this Risk record."))

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
                    risk._check_operational_readiness()
                elif risk.status in ("open", "mitigating") and target == "accepted":
                    if set(vals) - {"status", "accepted_by_id", "accepted_date"} or not risk.approver_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                        raise UserError(_("Only the Approver Designation holder may accept a risk."))
                    risk._check_operational_readiness()
                    risk._check_acceptance_evidence()
                    if vals.get("accepted_by_id") != self.env.user.id or not vals.get("accepted_date"):
                        raise ValidationError(_("Authenticated risk-acceptance metadata is required."))
                elif target == "resolved":
                    if set(vals) - {"status", "resolved_by_id", "resolved_date"}:
                        raise ValidationError(_("Save risk changes before using the controlled resolution transition."))
                    if not risk.approver_designation_id._user_holds_for_project(self.env.user, risk.project_id):
                        raise UserError(_("Only a current holder of the Approver Designation may resolve this risk."))
                    notes = vals.get("resolution_notes", risk.resolution_notes)
                    if not notes or vals.get("resolved_by_id") != self.env.user.id or not vals.get("resolved_date"):
                        raise ValidationError(_("Resolution notes and authenticated resolution metadata are required."))
                    risk._check_operational_readiness()
                    risk._check_acceptance_evidence()
                else:
                    raise ValidationError(_("Invalid Risk workflow transition."))
        result = super().write(vals)
        self._refresh_programme_risk_requirements()
        return result

    def action_start_mitigation(self):
        self.write({"status": "mitigating"})

    def action_accept(self):
        for risk in self:
            risk.write({
                "status": "accepted", "accepted_by_id": self.env.user.id,
                "accepted_date": fields.Date.context_today(risk),
            })

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

    def _check_approval_requirements(self):
        for ecn in self:
            for party, status, attachments, url in (
                (_("Supplier"), ecn.supplier_approval_status, ecn.supplier_evidence_ids, ecn.supplier_approval_evidence_url),
                (_("Customer"), ecn.customer_approval_status, ecn.customer_evidence_ids, ecn.customer_approval_evidence_url),
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
                    same_user_demo = (
                        ecn.submitted_by_id == self.env.user
                        and staging_self_approval_demo_enabled(self.env)
                    )
                    if (
                        not ecn.approver_designation_id._user_holds_for_project(self.env.user, ecn.project_id)
                        or (ecn.submitted_by_id == self.env.user and not same_user_demo)
                    ):
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
            same_user_demo = (
                ecn.submitted_by_id == self.env.user
                and staging_self_approval_demo_enabled(self.env)
            )
            if ecn.submitted_by_id == self.env.user and not same_user_demo:
                raise ValidationError(_("The same user cannot submit and approve an ECN."))
            ecn._check_approval_requirements()
            ecn.write({"status": "approved", "approved_by_id": self.env.user.id})
            if same_user_demo:
                record_staging_demo_transition(
                    ecn, "review", "approved", "staging_demo_approved"
                )

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
