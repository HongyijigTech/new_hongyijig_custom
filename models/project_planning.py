# -*- coding: utf-8 -*-

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_plan_baseline_ids = fields.One2many(
        "hjig.baseline", "project_id", domain=[("baseline_type", "=", "plan")],
        string="Project Plan Approvals",
    )
    hjig_active_plan_baseline_id = fields.Many2one(
        "hjig.baseline", compute="_compute_hjig_plan_health", string="Active Plan Baseline"
    )
    hjig_plan_task_count = fields.Integer(compute="_compute_hjig_plan_health")
    hjig_plan_missing_owner_count = fields.Integer(compute="_compute_hjig_plan_health")
    hjig_plan_missing_date_count = fields.Integer(compute="_compute_hjig_plan_health")
    hjig_plan_overdue_count = fields.Integer(compute="_compute_hjig_plan_health")
    hjig_plan_health = fields.Selection(
        [("empty", "No Tasks"), ("incomplete", "Incomplete"), ("ready", "Ready for Approval")],
        compute="_compute_hjig_plan_health",
    )

    @api.depends(
        "tasks.user_ids", "tasks.planned_date_begin", "tasks.date_deadline", "tasks.state",
        "hjig_baseline_ids.state", "hjig_baseline_ids.baseline_type",
    )
    def _compute_hjig_plan_health(self):
        today = fields.Datetime.now()
        for project in self:
            tasks = project.tasks.filtered(lambda task: not task.is_closed)
            approved = project.hjig_baseline_ids.filtered(
                lambda baseline: baseline.baseline_type == "plan" and baseline.state == "approved"
            ).sorted(lambda baseline: (baseline.effective_date or fields.Date.from_string("1900-01-01"), baseline.id), reverse=True)
            project.hjig_active_plan_baseline_id = approved[:1]
            project.hjig_plan_task_count = len(tasks)
            project.hjig_plan_missing_owner_count = len(tasks.filtered(lambda task: not task.user_ids))
            project.hjig_plan_missing_date_count = len(tasks.filtered(
                lambda task: not task.planned_date_begin or not task.date_deadline
            ))
            project.hjig_plan_overdue_count = len(tasks.filtered(
                lambda task: task.date_deadline and task.date_deadline < today
            ))
            if not tasks:
                project.hjig_plan_health = "empty"
            elif project.hjig_plan_missing_owner_count or project.hjig_plan_missing_date_count:
                project.hjig_plan_health = "incomplete"
            else:
                project.hjig_plan_health = "ready"

    def _hjig_plan_snapshot(self):
        self.ensure_one()
        tasks = self.tasks.sorted(lambda task: (task.sequence, task.id))
        return {
            "project_id": self.id,
            "project_name": self.name,
            "project_start": fields.Date.to_string(self.date_start) if self.date_start else False,
            "project_end": fields.Date.to_string(self.date) if self.date else False,
            "tasks": [{
                "id": task.id,
                "name": task.name,
                "owner_ids": sorted(task.user_ids.ids),
                "planned_start": fields.Datetime.to_string(task.planned_date_begin) if task.planned_date_begin else False,
                "deadline": fields.Datetime.to_string(task.date_deadline) if task.date_deadline else False,
                "milestone_id": task.milestone_id.id if task.milestone_id else False,
                "predecessor_ids": sorted(task.depend_on_ids.ids),
                "programme_activity": task.hjig_template_activity_id.code if task.hjig_template_activity_id else False,
            } for task in tasks],
        }

    def _assert_hjig_plan_ready(self):
        for project in self:
            if project.hjig_plan_health == "empty":
                raise ValidationError(_("The Project Plan has no tasks."))
            if project.hjig_plan_missing_owner_count or project.hjig_plan_missing_date_count:
                raise ValidationError(_(
                    "Project Plan is incomplete: %(owners)s task(s) lack an owner and %(dates)s task(s) lack start/deadline dates."
                ) % {
                    "owners": project.hjig_plan_missing_owner_count,
                    "dates": project.hjig_plan_missing_date_count,
                })
            invalid = project.tasks.filtered(
                lambda task: task.planned_date_begin and task.date_deadline
                and task.date_deadline < task.planned_date_begin
            )
            if invalid:
                raise ValidationError(_("Task deadlines cannot precede task start dates: %s") % ", ".join(invalid.mapped("name")))
        return True

    def action_validate_hjig_plan(self):
        self._assert_hjig_plan_ready()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Project Plan"), "message": _("Plan is complete and ready for controlled approval."), "type": "success"},
        }

    def action_open_hjig_plan_baselines(self):
        return self._hjig_project_record_action(
            "new_hongyijig_custom.action_hjig_baseline",
            extra_domain=[("baseline_type", "=", "plan")],
            extra_context={"default_baseline_type": "plan", "default_target_ref": "project.project,%s" % self.id},
        )


class HjigBaseline(models.Model):
    _inherit = "hjig.baseline"

    snapshot_json = fields.Json(readonly=True, copy=False)

    def write(self, vals):
        if "snapshot_json" in vals and not self.env.context.get("hjig_plan_snapshot"):
            raise ValidationError(_("Project Plan snapshots are generated only by the controlled baseline workflow."))
        return super().write(vals)

    def action_submit_review(self):
        for baseline in self.filtered(lambda item: item.baseline_type == "plan"):
            if baseline.target_ref != baseline.project_id:
                raise ValidationError(_("A Project Plan baseline must control its own Project record."))
            baseline.project_id._assert_hjig_plan_ready()
            payload = baseline.project_id._hjig_plan_snapshot()
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            baseline.with_context(hjig_plan_snapshot=True).write({
                "snapshot_json": payload,
                "snapshot_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            })
        return super().action_submit_review()
