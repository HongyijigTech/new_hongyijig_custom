# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HjigPlannedTeamResource(models.Model):
    _name = "hjig.planned.team.resource"
    _description = "Planned Team Resource"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "resource_type, name"

    name = fields.Char(required=True, tracking=True)
    email = fields.Char(tracking=True)
    resource_type = fields.Selection(
        [
            ("internal", "Internal Team"),
            ("customer", "Customer Representative"),
            ("supplier", "Supplier Representative"),
        ],
        required=True,
        default="internal",
        tracking=True,
    )
    planned_capacity = fields.Integer(
        string="Planned Concurrent Projects",
        default=1,
        help="Planning limit only. This does not create an Odoo login or grant workflow authority.",
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text()

    @api.constrains("planned_capacity")
    def _check_planned_capacity(self):
        if self.filtered(lambda resource: resource.planned_capacity < 1):
            raise ValidationError(_("Planned project capacity must be at least one."))


class HjigProjectDesignationAssignment(models.Model):
    _name = "hjig.project.designation.assignment"
    _description = "Project Designation Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, designation_id"

    project_id = fields.Many2one(
        "project.project", required=True, ondelete="cascade", index=True, tracking=True
    )
    designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", index=True, tracking=True
    )
    holder_ids = fields.Many2many(
        "res.users",
        "hjig_project_designation_user_rel",
        "assignment_id",
        "user_id",
        string="Authorised Role Holders",
        tracking=True,
    )
    planned_resource_ids = fields.Many2many(
        "hjig.planned.team.resource",
        "hjig_project_designation_planned_resource_rel",
        "assignment_id",
        "resource_id",
        string="Planned Resources (No Login)",
        tracking=True,
        help="Staffing plan only. Planned resources cannot execute or approve Odoo workflows.",
    )
    staffing_status = fields.Selection(
        [("missing", "Missing"), ("planned", "Planned - No Login"), ("ready", "Execution Ready")],
        compute="_compute_staffing_status",
        store=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    effective_from = fields.Date(default=fields.Date.context_today, tracking=True)
    effective_to = fields.Date(tracking=True)
    notes = fields.Text()

    _project_designation_unique = models.Constraint(
        "UNIQUE(project_id, designation_id)",
        "A designation may have only one governed assignment record per project.",
    )

    @api.depends("holder_ids", "planned_resource_ids")
    def _compute_staffing_status(self):
        for assignment in self:
            assignment.staffing_status = (
                "ready" if assignment.holder_ids
                else "planned" if assignment.planned_resource_ids
                else "missing"
            )

    def _sync_authorised_project_team(self):
        """A role assignment is the source of truth for governed project access.

        Adding the same person again on the project form was duplicate setup work and
        made a valid role assignment look incomplete. We only add current holders;
        we never remove an existing project-team member because that user may hold a
        different role or have separately approved project access.
        """
        for assignment in self.filtered(lambda item: item.active and item.holder_ids):
            missing = assignment.holder_ids - assignment.project_id.hjig_authorized_user_ids
            if missing:
                assignment.project_id.hjig_authorized_user_ids = [(4, user.id) for user in missing]
        return True

    @api.model_create_multi
    def create(self, vals_list):
        assignments = super().create(vals_list)
        assignments._sync_authorised_project_team()
        return assignments

    @api.constrains("active", "holder_ids", "planned_resource_ids", "effective_from", "effective_to")
    def _check_assignment_control(self):
        for assignment in self:
            if assignment.active and not (assignment.holder_ids or assignment.planned_resource_ids):
                raise ValidationError(_("An active project designation requires an authorised holder or a planned resource."))
            if (
                assignment.effective_from
                and assignment.effective_to
                and assignment.effective_to < assignment.effective_from
            ):
                raise ValidationError(_("The assignment end date cannot precede its start date."))

    def write(self, vals):
        governed = {
            "project_id", "designation_id", "holder_ids", "planned_resource_ids",
            "active", "effective_from", "effective_to",
        }
        if governed.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Only a Project Administrator may change project designation authority."))
        result = super().write(vals)
        if governed.intersection(vals):
            self._sync_authorised_project_team()
        return result

    def unlink(self):
        if not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Only a Project Administrator may delete project designation authority."))
        return super().unlink()


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_designation_assignment_ids = fields.One2many(
        "hjig.project.designation.assignment", "project_id", string="Designation Assignments"
    )
