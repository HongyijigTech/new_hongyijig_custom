# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    active = fields.Boolean(default=True, tracking=True)
    effective_from = fields.Date(default=fields.Date.context_today, tracking=True)
    effective_to = fields.Date(tracking=True)
    notes = fields.Text()

    _project_designation_unique = models.Constraint(
        "UNIQUE(project_id, designation_id)",
        "A designation may have only one governed assignment record per project.",
    )

    @api.constrains("active", "holder_ids", "effective_from", "effective_to")
    def _check_assignment_control(self):
        for assignment in self:
            if assignment.active and not assignment.holder_ids:
                raise ValidationError(_("An active project designation requires at least one role holder."))
            if (
                assignment.effective_from
                and assignment.effective_to
                and assignment.effective_to < assignment.effective_from
            ):
                raise ValidationError(_("The assignment end date cannot precede its start date."))

    def write(self, vals):
        governed = {"project_id", "designation_id", "holder_ids", "active", "effective_from", "effective_to"}
        if governed.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Only a Project Administrator may change project designation authority."))
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Only a Project Administrator may delete project designation authority."))
        return super().unlink()


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_designation_assignment_ids = fields.One2many(
        "hjig.project.designation.assignment", "project_id", string="Designation Assignments"
    )
