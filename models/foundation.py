# -*- coding: utf-8 -*-

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


def staging_self_approval_demo_enabled(env):
    """Allow a fully audited same-user demo only on the explicitly named database."""
    parameters = env["ir.config_parameter"].sudo()
    enabled = parameters.get_param(
        "new_hongyijig_custom.staging_self_approval_demo", "0"
    ) == "1"
    configured_database = parameters.get_param(
        "new_hongyijig_custom.staging_self_approval_database", ""
    )
    return enabled and configured_database == env.cr.dbname

HJIG_PROGRAMME_SELECTION = [
    ("launchguard_complete", "LaunchGuard Complete"),
    ("launchguard_design", "LaunchGuard Design"),
    ("launchguard_development", "LaunchGuard Development"),
    ("toollock_control", "ToolLock Control"),
    ("toollock_lite", "ToolLock Lite"),
    ("sourcebridge_only", "SourceBridge Only"),
]


class ProjectProject(models.Model):
    _inherit = "project.project"

    _HJIG_PROGRAMME_STAGE_CODES = {
        "launchguard_complete": (
            "PA-00", "TG-01", "TG-02", "TG-03", "TG-04",
            "TG-05", "TG-06", "TG-07", "TG-08", "TG-09",
        ),
        "launchguard_design": ("PA-00", "TG-01"),
        "launchguard_development": (
            "TG-01", "TG-02", "TG-03", "TG-04", "TG-05",
            "TG-06", "TG-07", "TG-08", "TG-09",
        ),
        "toollock_control": (
            "TG-01", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-09",
        ),
        "toollock_lite": (),
        "sourcebridge_only": (),
    }

    hjig_programme = fields.Selection(
        HJIG_PROGRAMME_SELECTION,
        string="Hongyi Programme",
        required=True,
        default="launchguard_complete",
        tracking=True,
    )
    hjig_allowed_stage_ids = fields.Many2many(
        "hjig.launchguard.stage", compute="_compute_hjig_allowed_stages",
        string="Applicable Governance Stages",
    )
    hjig_current_stage_id = fields.Many2one(
        "hjig.launchguard.stage", string="Current Governance Stage",
        ondelete="restrict", tracking=True, readonly=True,
        help="Last stage cleared by an approved GO decision. It cannot be set manually.",
    )
    hjig_pending_programme = fields.Selection(
        HJIG_PROGRAMME_SELECTION,
        string="Proposed Programme Route", tracking=True,
    )
    hjig_programme_change_reason = fields.Text(string="Route Change Reason", tracking=True)
    hjig_programme_commercial_review = fields.Text(
        string="Commercial Impact Review", tracking=True,
        help="Record the reviewed cost, revenue, liability and customer/supplier commercial impact, including No Impact.",
    )
    hjig_programme_change_authority_id = fields.Many2one(
        "hjig.governance.designation", string="PMO Route-Change Authority",
        ondelete="restrict", tracking=True,
    )
    hjig_programme_change_approval_id = fields.Many2one(
        "hjig.approval", string="Route-Change Approval", readonly=True, copy=False, ondelete="restrict",
    )
    hjig_programme_change_status = fields.Selection(
        [("none", "No Change"), ("pending", "Pending Approval"),
         ("approved", "Approved"), ("rejected", "Rejected")],
        default="none", required=True, readonly=True, copy=False, tracking=True,
    )

    hjig_authorized_user_ids = fields.Many2many(
        "res.users",
        "hjig_project_authorized_user_rel",
        "project_id",
        "user_id",
        string="Hongyi Project Team",
        tracking=True,
        help="Users allowed to access Hongyi governed records for this project.",
    )
    hjig_baseline_ids = fields.One2many("hjig.baseline", "project_id", string="Controlled Baselines")
    hjig_evidence_ids = fields.One2many("hjig.evidence.link", "project_id", string="Evidence")
    hjig_approval_ids = fields.One2many("hjig.approval", "project_id", string="Approvals")
    hjig_baseline_count = fields.Integer(compute="_compute_hjig_operating_counts")
    hjig_sor_count = fields.Integer(compute="_compute_hjig_operating_counts")
    hjig_gate_count = fields.Integer(compute="_compute_hjig_operating_counts")
    hjig_tooling_execution_count = fields.Integer(compute="_compute_hjig_operating_counts")
    hjig_inspection_count = fields.Integer(compute="_compute_hjig_operating_counts")
    hjig_commercial_link_count = fields.Integer(
        compute="_compute_hjig_commercial_count",
        groups="new_hongyijig_custom.group_hjig_commercial_user",
    )

    def _hjig_allowed_stage_codes(self):
        self.ensure_one()
        return self._HJIG_PROGRAMME_STAGE_CODES.get(self.hjig_programme, ())

    @api.depends("hjig_programme")
    def _compute_hjig_allowed_stages(self):
        stage_model = self.env["hjig.launchguard.stage"]
        for project in self:
            codes = project._hjig_allowed_stage_codes()
            project.hjig_allowed_stage_ids = stage_model.search([
                ("code", "in", list(codes)), ("active", "=", True),
            ]) if codes else stage_model.browse()

    @api.constrains("hjig_programme", "hjig_current_stage_id")
    def _check_hjig_programme_routing(self):
        for project in self:
            allowed_codes = set(project._hjig_allowed_stage_codes())
            if project.hjig_current_stage_id and project.hjig_current_stage_id.code not in allowed_codes:
                raise ValidationError(_("The current stage is not applicable to the selected Hongyi Programme."))
            invalid_gates = self.env["hjig.gate"].search([
                ("project_id", "=", project.id), ("stage_id.code", "not in", list(allowed_codes)),
            ], limit=1)
            if invalid_gates:
                raise ValidationError(_(
                    "The Programme cannot change while gate %s belongs to a stage outside the selected route."
                ) % invalid_gates.code)

    def _compute_hjig_operating_counts(self):
        models_by_field = {
            "hjig_baseline_count": "hjig.baseline",
            "hjig_sor_count": "hjig.sor",
            "hjig_gate_count": "hjig.gate",
            "hjig_tooling_execution_count": "hjig.tooling.execution",
            "hjig_inspection_count": "hjig.inspection",
        }
        for field_name in models_by_field:
            for project in self:
                project[field_name] = 0
        if not self.ids:
            return
        for field_name, model_name in models_by_field.items():
            grouped = self.env[model_name]._read_group(
                [("project_id", "in", self.ids)], ["project_id"], ["__count"],
            )
            counts = {project.id: count for project, count in grouped}
            for project in self:
                project[field_name] = counts.get(project.id, 0)

    def _compute_hjig_commercial_count(self):
        for project in self:
            project.hjig_commercial_link_count = 0
        if not self.ids:
            return
        grouped = self.env["hjig.commercial.link"]._read_group(
            [("project_id", "in", self.ids)], ["project_id"], ["__count"],
        )
        counts = {project.id: count for project, count in grouped}
        for project in self:
            project.hjig_commercial_link_count = counts.get(project.id, 0)

    def _hjig_project_record_action(self, xml_id, extra_domain=None, extra_context=None):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["domain"] = [("project_id", "=", self.id)] + list(extra_domain or [])
        action["context"] = {"default_project_id": self.id, **(extra_context or {})}
        return action

    def action_open_hjig_baselines(self):
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_baseline")

    def action_open_hjig_sor(self):
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_sor")

    def action_open_hjig_gates(self):
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_gate")

    def action_open_hjig_tooling(self):
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_tooling_execution")

    def action_open_hjig_inspections(self):
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_inspection")

    def action_open_hjig_commercial_links(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_commercial_user"):
            raise UserError(_("Hongyi Commercial Records access is required."))
        return self._hjig_project_record_action("new_hongyijig_custom.action_hjig_commercial_link_all")

    def action_request_hjig_programme_change(self):
        if not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only a Project Manager may request a Programme route change."))
        for project in self:
            project._lock_hjig_programme_route()
            if project.hjig_programme_change_status == "pending":
                raise UserError(_("A Programme route change is already pending."))
            if not project.hjig_pending_programme or project.hjig_pending_programme == project.hjig_programme:
                raise ValidationError(_("Select a different proposed Programme route."))
            if not (project.hjig_programme_change_reason or "").strip():
                raise ValidationError(_("A Programme route-change reason is required."))
            if not (project.hjig_programme_commercial_review or "").strip():
                raise ValidationError(_("A documented commercial impact review is required, including when there is no impact."))
            authority = project.hjig_programme_change_authority_id
            if not authority or authority.category != "governance":
                raise ValidationError(_("Select a Governance / PMO designation as the route-change authority."))
            snapshot_values = {
                "from_programme": project.hjig_programme,
                "to_programme": project.hjig_pending_programme,
                "reason": project.hjig_programme_change_reason,
                "commercial_review": project.hjig_programme_commercial_review,
                "current_stage": project.hjig_current_stage_id.code if project.hjig_current_stage_id else False,
            }
            snapshot = json.dumps(snapshot_values, sort_keys=True, separators=(",", ":"))
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": project.id,
                "target_ref": "project.project,%s" % project.id,
                "approval_type": "other",
                "authority_designation_id": authority.id,
                "requested_by_id": self.env.user.id,
            })
            approval.with_context(**workflow_context()).write({
                "request_snapshot": snapshot,
                "request_snapshot_hash": hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            })
            project.with_context(**workflow_context()).write({
                "hjig_programme_change_approval_id": approval.id,
                "hjig_programme_change_status": "pending",
            })

    def action_apply_hjig_programme_change(self):
        for project in self:
            project._lock_hjig_programme_route()
            approval = project.hjig_programme_change_approval_id
            if project.hjig_programme_change_status != "pending" or not approval:
                raise UserError(_("The Project has no pending Programme route-change decision."))
            approval._lock_transition()
            if (
                approval.approval_type != "other"
                or approval.target_ref != project
                or approval.project_id != project
                or approval.authority_designation_id != project.hjig_programme_change_authority_id
            ):
                raise ValidationError(_(
                    "The linked approval does not match this Project route-change request and authority."
                ))
            if approval.state == "approved":
                snapshot = approval.request_snapshot or ""
                if not snapshot or hashlib.sha256(snapshot.encode("utf-8")).hexdigest() != approval.request_snapshot_hash:
                    raise ValidationError(_("The approved Programme route-change snapshot is missing or invalid."))
                try:
                    approved_values = json.loads(snapshot)
                except (TypeError, ValueError) as error:
                    raise ValidationError(_("The approved Programme route-change snapshot is not valid JSON.")) from error
                new_programme = approved_values.get("to_programme")
                if (
                    approved_values.get("from_programme") != project.hjig_programme
                    or new_programme not in self._HJIG_PROGRAMME_STAGE_CODES
                ):
                    raise ValidationError(_(
                        "The approved Programme route-change snapshot does not match the Project's current route."
                    ))
                allowed_codes = set(self._HJIG_PROGRAMME_STAGE_CODES.get(new_programme, ()))
                invalid_gate = self.env["hjig.gate"].search([
                    ("project_id", "=", project.id),
                    ("stage_id.code", "not in", list(allowed_codes)),
                ], limit=1)
                if invalid_gate:
                    raise ValidationError(_(
                        "Route change cannot be applied while decided gate %s is outside the proposed route."
                    ) % invalid_gate.code)
                eligible_go_gates = self.env["hjig.gate"].search([
                    ("project_id", "=", project.id), ("state", "=", "go"),
                    ("stage_id.code", "in", list(allowed_codes)),
                    ("stage_id.active", "=", True),
                ])
                route_order = list(self._HJIG_PROGRAMME_STAGE_CODES.get(new_programme, ()))
                last_go = max(
                    eligible_go_gates,
                    key=lambda gate: (route_order.index(gate.stage_id.code), gate.cycle),
                    default=self.env["hjig.gate"].browse(),
                )
                previous_programme = project.hjig_programme
                project.with_context(**workflow_context()).write({
                    "hjig_programme": new_programme,
                    "hjig_current_stage_id": last_go.stage_id.id if last_go else False,
                    "hjig_programme_change_status": "approved",
                })
                self.env["hjig.transition.log"].sudo().create({
                    "project_id": project.id, "target_ref": "project.project,%s" % project.id,
                    "from_state": previous_programme, "to_state": new_programme,
                    "decision": "programme_route_changed", "actor_id": self.env.user.id,
                    "approval_id": approval.id, "reason": approved_values.get("reason"),
                })
            elif approval.state == "rejected":
                project.with_context(**workflow_context()).write({
                    "hjig_programme_change_status": "rejected",
                })
            else:
                raise UserError(_("The Programme route-change approval is still pending."))

    def _lock_hjig_programme_route(self):
        """Serialize route changes with all gate transitions for this Project."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            (self.id, 0),
        )
        self.env.cr.execute(
            "SELECT id FROM project_project WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        self.invalidate_recordset([
            "hjig_programme", "hjig_current_stage_id", "hjig_pending_programme",
            "hjig_programme_change_reason", "hjig_programme_commercial_review",
            "hjig_programme_change_authority_id", "hjig_programme_change_approval_id",
            "hjig_programme_change_status",
        ])

    @api.model_create_multi
    def create(self, vals_list):
        governed = {"hjig_authorized_user_ids", "hjig_programme"}
        controlled_sseries_activation = (
            self.env.su and self.env.context.get("hjig_sseries_activation")
        )
        if any(governed.intersection(vals) for vals in vals_list) and not self.env.user.has_group(
            "project.group_project_manager"
        ) and not controlled_sseries_activation:
            raise UserError(_("Only Project Managers may configure the governed Hongyi project route and team."))
        if any(vals.get("hjig_current_stage_id") for vals in vals_list):
            raise ValidationError(_("The current governance stage can only be established by an approved GO decision."))
        for vals in vals_list:
            vals["hjig_current_stage_id"] = False
            vals["hjig_programme_change_status"] = "none"
        return super().create(vals_list)

    def write(self, vals):
        workflow_only = {
            "hjig_programme", "hjig_current_stage_id",
            "hjig_programme_change_approval_id", "hjig_programme_change_status",
        }
        if workflow_only.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Programme route, stage and decision fields may only change through governed actions."))
        manager_fields = {
            "hjig_authorized_user_ids", "hjig_pending_programme",
            "hjig_programme_change_reason", "hjig_programme_commercial_review",
            "hjig_programme_change_authority_id",
        }
        if manager_fields.intersection(vals) and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only Project Managers may configure the governed Hongyi project route and team."))
        if manager_fields.intersection(vals):
            for project in self:
                project._lock_hjig_programme_route()
                if project.hjig_programme_change_status == "pending":
                    raise ValidationError(_("Programme route-change inputs are locked while approval is pending."))
        return super().write(vals)


class HjigTargetMixin(models.AbstractModel):
    _name = "hjig.target.mixin"
    _description = "Hongyi Governed Target Mixin"

    @api.model
    def _selection_target_model(self):
        """Modules extend this method when they add a governed operational model."""
        targets = [
            ("project.project", "Project"),
            ("project.task", "Project Task"),
            ("hjig.project.document", "Controlled Project Document"),
            ("hjig.baseline", "Controlled Baseline"),
            ("hjig.evidence.link", "Evidence"),
            ("hjig.approval", "Controlled Approval"),
        ]
        # These records already exist in some Hongyi databases as governed or
        # Studio-backed models.  Expose them when present instead of creating
        # replacement Risk, ECN, Mould Planning, Part, or Mould Register models.
        adapters = [
            ("x_mould", "Project Mould Planning Form"),
            ("x_mould_part", "Mould Planning Component / Part"),
            ("hjig.final.mould.plan", "Final Mould Plan"),
            ("hjig.mould.register", "Project Mould Register"),
            ("hjig.project.risk", "Project Risk Register"),
            ("s.series.risk", "Risk Register"),
            ("hjig.project.issue", "Project Issue / Design Challenge Register"),
            ("hjig.project.ecn", "Engineering Change Notice Register"),
            ("hjig.sourcebridge.component", "SourceBridge Sourcing Component"),
        ]
        compatible_adapters = []
        for model, label in adapters:
            if model not in self.env.registry:
                continue
            candidate = self.env[model]
            project_field = candidate._fields.get("project_id") or candidate._fields.get("x_project_id")
            engagement_field = candidate._fields.get("engagement_id")
            engagement_project_field = False
            if (
                engagement_field
                and engagement_field.type == "many2one"
                and engagement_field.comodel_name in self.env.registry
            ):
                engagement_project_field = self.env[engagement_field.comodel_name]._fields.get("project_id")
            if (
                project_field
                and project_field.type == "many2one"
                and project_field.comodel_name == "project.project"
            ) or (
                engagement_project_field
                and engagement_project_field.type == "many2one"
                and engagement_project_field.comodel_name == "project.project"
            ):
                compatible_adapters.append((model, label))
        return targets + compatible_adapters

    def _check_target_project(self, target_record, project):
        if target_record._name == "project.project":
            target_project = target_record
        else:
            target_project = (
                target_record.project_id if "project_id" in target_record._fields
                else target_record.x_project_id if "x_project_id" in target_record._fields
                else target_record.engagement_id.project_id
                if "engagement_id" in target_record._fields and target_record.engagement_id
                and "project_id" in target_record.engagement_id._fields
                else False
            )
        if not target_project or target_project != project:
            raise ValidationError(_("The governed target must belong to the selected project."))


class HjigBaseline(models.Model):
    _name = "hjig.baseline"
    _description = "Hongyi Controlled Baseline"
    _inherit = ["mail.thread", "mail.activity.mixin", "hjig.target.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one(
        "project.project", required=True, ondelete="restrict", index=True, tracking=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(
        selection="_selection_target_model", required=True, string="Controlled Record", tracking=True
    )
    baseline_type = fields.Selection(
        [
            ("sor", "SOR / Scope"),
            ("plan", "Project Plan"),
            ("bop", "BOP"),
            ("mould", "Mould Plan"),
            ("other", "Other Controlled Baseline"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    revision = fields.Char(required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
            ("superseded", "Superseded"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    effective_date = fields.Date(tracking=True)
    change_reason = fields.Text(tracking=True)
    snapshot_hash = fields.Char(copy=False, tracking=True)
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation",
        string="Approval Authority",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    supersedes_id = fields.Many2one("hjig.baseline", ondelete="restrict", tracking=True)
    superseded_by_id = fields.Many2one(
        "hjig.baseline", ondelete="restrict", readonly=True, copy=False
    )
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")

    _code_unique = models.Constraint("UNIQUE(code)", "Baseline code must be unique.")
    _target_revision_unique = models.Constraint(
        "UNIQUE(project_id, target_ref, baseline_type, revision)",
        "This baseline revision already exists for the controlled record.",
    )

    _LOCKED_FIELDS = {
        "project_id", "target_ref", "baseline_type", "revision", "effective_date",
        "change_reason", "snapshot_hash", "approval_authority_designation_id", "supersedes_id",
        "approval_id",
    }

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.baseline") or _("New")
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id", "supersedes_id")
    def _check_governed_target(self):
        for baseline in self:
            baseline._check_target_project(baseline.target_ref, baseline.project_id)
            if baseline.supersedes_id:
                if baseline.supersedes_id.project_id != baseline.project_id:
                    raise ValidationError(_("A baseline can only supersede a baseline in the same project."))
                if baseline.supersedes_id.target_ref != baseline.target_ref:
                    raise ValidationError(_("A revision must supersede a baseline for the same controlled record."))
                if baseline.supersedes_id.baseline_type != baseline.baseline_type:
                    raise ValidationError(_("A revision must keep the same baseline type."))

    def write(self, vals):
        if "approval_id" in vals and not is_workflow_context(self.env):
            raise ValidationError(_("The linked approval is controlled by the baseline workflow."))
        if "state" in vals and not is_workflow_context(self.env):
            if any(record.state != vals["state"] for record in self):
                raise ValidationError(_("Baseline state may only change through controlled workflow actions."))
        if self._LOCKED_FIELDS.intersection(vals) and any(
            record.state in ("approved", "superseded") for record in self
        ):
            raise ValidationError(_("Approved or superseded baselines are read-only. Create a new revision."))
        return super().write(vals)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only Draft baselines may be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for baseline in self:
            if baseline.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected baselines can be submitted."))
            previous_state = baseline.state
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": baseline.project_id.id,
                "target_ref": "%s,%s" % (baseline._name, baseline.id),
                "approval_type": "baseline",
                "authority_designation_id": baseline.approval_authority_designation_id.id,
                "requested_by_id": self.env.user.id,
            })
            baseline.with_context(**workflow_context()).write({
                "state": "review",
                "approval_id": approval.id,
            })
            self.env["hjig.transition.log"].sudo().create({
                "project_id": baseline.project_id.id,
                "target_ref": "%s,%s" % (baseline._name, baseline.id),
                "from_state": previous_state,
                "to_state": "review",
                "decision": "submitted",
                "actor_id": self.env.user.id,
                "approval_id": approval.id,
            })

    def action_apply_approval(self):
        for baseline in self:
            if baseline.state != "review" or not baseline.approval_id:
                raise UserError(_("The baseline has no completed approval to apply."))
            if baseline.approval_id.state == "approved":
                if not baseline.effective_date:
                    raise ValidationError(_("Effective Date is required before approval."))
                if baseline.supersedes_id:
                    if baseline.supersedes_id.state != "approved":
                        raise ValidationError(_("The superseded baseline must currently be Approved."))
                    baseline.supersedes_id.with_context(**workflow_context()).write({
                        "state": "superseded", "superseded_by_id": baseline.id,
                    })
                baseline.with_context(**workflow_context()).write({"state": "approved"})
                target_state = "approved"
            elif baseline.approval_id.state == "rejected":
                baseline.with_context(**workflow_context()).write({"state": "rejected"})
                target_state = "rejected"
            else:
                raise UserError(_("The approval decision is still pending."))
            self.env["hjig.transition.log"].sudo().create({
                "project_id": baseline.project_id.id,
                "target_ref": "%s,%s" % (baseline._name, baseline.id),
                "from_state": "review",
                "to_state": target_state,
                "decision": baseline.approval_id.state,
                "actor_id": self.env.user.id,
                "approval_id": baseline.approval_id.id,
                "reason": baseline.approval_id.decision_reason,
            })


class HjigEvidenceLink(models.Model):
    _name = "hjig.evidence.link"
    _description = "Hongyi Evidence Link"
    _inherit = ["mail.thread", "mail.activity.mixin", "hjig.target.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Evidence For")
    evidence_type = fields.Char(required=True, tracking=True)
    attachment_id = fields.Many2one("ir.attachment", ondelete="restrict", tracking=True)
    source_url = fields.Char(tracking=True)
    source_party = fields.Selection(
        [("customer", "Customer"), ("hongyi", "Hongyi"), ("supplier", "Supplier")],
        required=True,
        tracking=True,
    )
    source_date = fields.Date(tracking=True)
    revision = fields.Char(tracking=True)
    verification_state = fields.Selection(
        [("unverified", "Unverified"), ("accepted", "Accepted"), ("rejected", "Rejected")],
        default="unverified",
        required=True,
        tracking=True,
    )
    verifier_id = fields.Many2one("res.users", readonly=True, copy=False)
    verification_date = fields.Datetime(readonly=True, copy=False)
    notes = fields.Text()

    _code_unique = models.Constraint("UNIQUE(code)", "Evidence code must be unique.")

    _CONTROLLED_FIELDS = {
        "project_id", "target_ref", "evidence_type", "attachment_id", "source_url",
        "source_party", "source_date", "revision",
    }

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("attachment_id") and not (vals.get("source_url") or "").strip():
                raise ValidationError(_("Evidence requires an attachment or a source link."))
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.evidence.link") or _("New")
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id")
    def _check_governed_target(self):
        for evidence in self:
            evidence._check_target_project(evidence.target_ref, evidence.project_id)

    @api.constrains("attachment_id", "source_url")
    def _check_evidence_source(self):
        for evidence in self:
            if not evidence.attachment_id and not (evidence.source_url or "").strip():
                raise ValidationError(_("Evidence requires an attachment or a source link."))

    def write(self, vals):
        workflow_fields = {"verification_state", "verifier_id", "verification_date"}
        if workflow_fields.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Evidence verification fields may only change through verification actions."))
        if self._CONTROLLED_FIELDS.intersection(vals) and any(
            record.verification_state != "unverified" for record in self
        ):
            raise ValidationError(_("Verified evidence is read-only. Add replacement evidence instead."))
        return super().write(vals)

    def _record_verification(self, state):
        demo_override = staging_self_approval_demo_enabled(self.env)
        if (
            not demo_override
            and not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver")
        ):
            raise UserError(_("Only authorised Governance Approvers may verify evidence."))
        for evidence in self:
            if evidence.verification_state != "unverified":
                raise UserError(_("Only Unverified evidence can be accepted or rejected."))
            same_user_override = demo_override and evidence.create_uid == self.env.user
            if evidence.create_uid == self.env.user and not same_user_override:
                raise ValidationError(_("The person who created or uploaded evidence cannot verify it."))
            evidence.with_context(**workflow_context()).write({
                "verification_state": state,
                "verifier_id": self.env.user.id,
                "verification_date": fields.Datetime.now(),
            })
            self.env["hjig.transition.log"].sudo().create({
                "project_id": evidence.project_id.id,
                "target_ref": "%s,%s" % (evidence._name, evidence.id),
                "from_state": "unverified",
                "to_state": state,
                "decision": state,
                "actor_id": self.env.user.id,
                "reason": (
                    "STAGING TRAINING OVERRIDE: evidence creator performed the demonstration verification."
                    if same_user_override else False
                ),
            })

    def action_accept(self):
        self._record_verification("accepted")

    def action_reject(self):
        self._record_verification("rejected")

    def _assert_accepted(self):
        unaccepted = self.filtered(lambda evidence: evidence.verification_state != "accepted")
        if unaccepted:
            raise ValidationError(_(
                "Evidence must be independently Accepted before it can support a controlled result: %s"
            ) % ", ".join(unaccepted.mapped("code")))

    def unlink(self):
        if any(evidence.verification_state != "unverified" for evidence in self):
            raise UserError(_("Verified evidence cannot be deleted. Add replacement evidence instead."))
        return super().unlink()


class HjigApproval(models.Model):
    _name = "hjig.approval"
    _description = "Hongyi Controlled Approval"
    _inherit = ["mail.thread", "mail.activity.mixin", "hjig.target.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Approval For")
    approval_type = fields.Selection(
        [
            ("baseline", "Baseline Approval"),
            ("engineering", "Engineering Approval"),
            ("commercial", "Commercial Approval"),
            ("gate", "Gate Decision"),
            ("other", "Other Approval"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    requested_by_id = fields.Many2one("res.users", required=True, readonly=True, copy=False)
    requested_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, copy=False)
    request_snapshot_hash = fields.Char(readonly=True, copy=False, index=True)
    request_snapshot = fields.Text(
        readonly=True, copy=False,
        groups="new_hongyijig_custom.group_hjig_governance_approver,project.group_project_manager",
    )
    state = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="pending",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    approver_id = fields.Many2one("res.users", readonly=True, copy=False)
    decision_date = fields.Datetime(readonly=True, copy=False)
    decision_reason = fields.Text(tracking=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Approval code must be unique.")

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals.setdefault("requested_by_id", self.env.user.id)
            vals["state"] = "pending"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.approval") or _("New")
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id")
    def _check_governed_target(self):
        for approval in self:
            approval._check_target_project(approval.target_ref, approval.project_id)

    def write(self, vals):
        workflow_fields = {
            "state", "approver_id", "decision_date", "requested_by_id", "requested_date",
            "request_snapshot_hash", "request_snapshot",
        }
        if workflow_fields.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Approval audit fields may only change through decision actions."))
        identity_fields = {
            "project_id", "target_ref", "approval_type", "authority_designation_id",
            "requested_by_id", "requested_date",
        }
        if identity_fields.intersection(vals):
            raise ValidationError(_("Approval request identity is immutable after creation."))
        if "decision_reason" in vals:
            for approval in self:
                approval._lock_transition()
                if approval.state != "pending":
                    raise ValidationError(_("A completed approval is read-only."))
        if any(record.state != "pending" for record in self):
            protected = {
                "project_id", "target_ref", "approval_type", "authority_designation_id",
                "requested_by_id", "requested_date", "request_snapshot_hash", "request_snapshot", "decision_reason",
                "state", "approver_id", "decision_date",
            }
            if protected.intersection(vals):
                raise ValidationError(_("A completed approval is read-only."))
        return super().write(vals)

    def _check_decision_authority(self):
        demo_override = staging_self_approval_demo_enabled(self.env)
        if (
            not demo_override
            and not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver")
        ):
            raise UserError(_("Only authorised Hongyi Governance Approvers may decide this request."))
        for approval in self:
            target = approval.sudo().target_ref
            if (
                approval.approval_type == "commercial"
                and target
                and target._name == "hjig.commercial.link"
                and not self.env.user.has_group("new_hongyijig_custom.group_hjig_commercial_user")
            ):
                raise UserError(_(
                    "Commercial decisions require Hongyi Commercial Records access so the approver can inspect the immutable submission snapshot."
                ))
            if (
                not demo_override
                and approval.authority_designation_id
                and self.env.user not in approval.authority_designation_id.holder_ids
            ):
                raise UserError(_("You do not hold the required approval designation."))
            if approval.requested_by_id == self.env.user and not demo_override:
                raise ValidationError(_("The requester cannot approve or reject their own request."))

    def _lock_transition(self):
        """Serialize approval decisions with cancellation and gate application."""
        self.ensure_one()
        target = self.sudo().target_ref
        if self.approval_type == "gate" and target and target._name == "hjig.gate":
            self.env.cr.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)",
                (target.project_id.id, 0),
            )
            self.env.cr.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)",
                (target.project_id.id, target.stage_id.id),
            )
        self.env.cr.execute(
            "SELECT id FROM hjig_approval WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        self.invalidate_recordset(["state", "approver_id", "decision_date", "decision_reason"])

    def _record_decision(self, state):
        self._check_decision_authority()
        demo_override = staging_self_approval_demo_enabled(self.env)
        for approval in self:
            approval._lock_transition()
            if approval.state != "pending":
                raise UserError(_("Only Pending approvals can be decided."))
            if state == "rejected" and not (approval.decision_reason or "").strip():
                raise ValidationError(_("A rejection reason is required."))
            if (
                state == "approved"
                and approval.approval_type == "gate"
                and approval.target_ref
                and approval.target_ref._name == "hjig.gate"
                and approval.target_ref.readiness == "warn"
                and not (approval.decision_reason or "").strip()
            ):
                raise ValidationError(_("A GO decision with warnings requires the approver's acceptance reason."))
            approval.with_context(**workflow_context()).write({
                "state": state,
                "approver_id": self.env.user.id,
                "decision_date": fields.Datetime.now(),
            })
            self.env["hjig.transition.log"].sudo().create({
                "project_id": approval.project_id.id,
                "target_ref": "%s,%s" % (approval._name, approval.id),
                "from_state": "pending",
                "to_state": state,
                "decision": state,
                "actor_id": self.env.user.id,
                "approval_id": approval.id,
                "reason": (
                    "STAGING TRAINING OVERRIDE: requester performed the demonstration decision."
                    if demo_override and approval.requested_by_id == self.env.user
                    else approval.decision_reason
                ),
            })

    def action_approve(self):
        self._record_decision("approved")

    def action_reject(self):
        self._record_decision("rejected")

    def unlink(self):
        raise UserError(_("Approval records are retained as audit history and cannot be deleted."))


class HjigTransitionLog(models.Model):
    _name = "hjig.transition.log"
    _description = "Hongyi Transition Audit Log"
    _inherit = ["hjig.target.mixin"]
    _order = "transition_date desc, id desc"

    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    target_ref = fields.Reference(selection="_selection_target_model", required=True, string="Transition For")
    from_state = fields.Char(required=True)
    to_state = fields.Char(required=True)
    decision = fields.Char(required=True)
    actor_id = fields.Many2one("res.users", required=True, readonly=True)
    transition_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    approval_id = fields.Many2one("hjig.approval", ondelete="restrict", readonly=True)
    reason = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("actor_id", self.env.user.id)
        return super().create(vals_list)

    @api.constrains("target_ref", "project_id")
    def _check_governed_target(self):
        for transition in self:
            transition._check_target_project(transition.target_ref, transition.project_id)

    def write(self, vals):
        raise UserError(_("Transition history is append-only."))

    def unlink(self):
        raise UserError(_("Transition history is append-only and cannot be deleted."))
