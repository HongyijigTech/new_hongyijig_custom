# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HjigProgrammeTemplate(models.Model):
    _name = "hjig.programme.template"
    _description = "Governed Programme Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    version_ids = fields.One2many("hjig.programme.template.version", "template_id")
    active = fields.Boolean(default=True, tracking=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Programme template code must be unique.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        if {"code", "owner_designation_id", "approver_designation_id"}.intersection(vals):
            if self.version_ids.filtered(lambda version: version.state == "approved"):
                raise ValidationError(
                    _("A programme with an approved version cannot have its governed identity rewritten.")
                )
        return super().write(vals)

    def action_open_versions(self):
        """Open governed versions as normal records instead of nested pop-ups."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("%s — Governed Versions") % self.name,
            "res_model": "hjig.programme.template.version",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
            "context": {"default_template_id": self.id},
        }

    @api.constrains("owner_designation_id", "approver_designation_id")
    def _check_designation_separation(self):
        for template in self:
            if template.owner_designation_id == template.approver_designation_id:
                raise ValidationError(_("Programme owner and approver designations must be different."))


class HjigProgrammeTemplateVersion(models.Model):
    _name = "hjig.programme.template.version"
    _description = "Governed Programme Template Version"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "template_id, effective_from desc, version desc"

    name = fields.Char(compute="_compute_name", store=True)
    template_id = fields.Many2one(
        "hjig.programme.template", required=True, ondelete="restrict", index=True, tracking=True
    )
    version = fields.Char(required=True, default="1.0", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
            ("retired", "Retired"),
        ],
        required=True,
        default="draft",
        index=True,
        tracking=True,
    )
    is_current = fields.Boolean(default=False, index=True, tracking=True)
    effective_from = fields.Date(tracking=True)
    effective_to = fields.Date(tracking=True)
    source_project_id = fields.Many2one(
        "project.project",
        string="Legacy Template Project",
        ondelete="restrict",
        tracking=True,
        help="Read-only migration trace to the legacy template project.",
    )
    legacy_source_database = fields.Char(
        readonly=True,
        copy=False,
        help="Database from which this draft programme DNA was reconciled.",
    )
    legacy_source_project_id = fields.Integer(readonly=True, copy=False)
    legacy_source_task_count = fields.Integer(readonly=True, copy=False)
    gate_line_ids = fields.One2many("hjig.programme.template.gate", "version_id")
    activity_line_ids = fields.One2many("hjig.programme.template.activity", "version_id")
    artifact_rule_ids = fields.One2many("hjig.programme.template.artifact", "version_id")
    dependency_rule_ids = fields.One2many(
        "hjig.programme.template.dependency.rule", "version_id"
    )
    dependency_review_status = fields.Selection(
        [("unreviewed", "Unreviewed"), ("verified", "Verified")],
        required=True,
        default="unreviewed",
        tracking=True,
        help="A verified status means the activity dependency map was reviewed against the approved programme DNA.",
    )
    evidence_review_status = fields.Selection(
        [("unreviewed", "Unreviewed"), ("verified", "Verified")],
        required=True,
        default="unreviewed",
        tracking=True,
        help="A verified status means every mandatory SOP/Form requirement was reviewed gate by gate.",
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    approved_on = fields.Datetime(readonly=True, tracking=True)
    definition_hash = fields.Char(readonly=True, copy=False, index=True)
    active = fields.Boolean(default=True, tracking=True)

    _template_version_unique = models.Constraint(
        "UNIQUE(template_id, version)",
        "A programme version must be unique within its template.",
    )

    @api.depends("template_id.name", "version")
    def _compute_name(self):
        for record in self:
            record.name = "%s v%s" % (record.template_id.name or "Programme", record.version or "")

    def _assert_mutable(self):
        if self.filtered(lambda record: record.state in ("approved", "retired")):
            raise ValidationError(
                _("Approved or retired programme versions are immutable. Create a new version instead.")
            )

    def write(self, vals):
        governed = {
            "template_id", "version", "effective_from", "effective_to", "source_project_id",
            "legacy_source_database", "legacy_source_project_id", "legacy_source_task_count",
            "gate_line_ids", "activity_line_ids", "artifact_rule_ids",
            "dependency_rule_ids",
            "dependency_review_status", "evidence_review_status",
        }
        retiring = vals.get("state") == "retired"
        retirement_date_only = governed.intersection(vals).issubset({"effective_to"})
        if governed.intersection(vals) and not (
            retiring and retirement_date_only and all(record.state == "approved" for record in self)
        ):
            self._assert_mutable()
        if "state" in vals and not self.env.context.get("hjig_programme_lifecycle"):
            raise ValidationError(_("Use the governed programme lifecycle actions to change state."))
        if "is_current" in vals and not self.env.context.get("hjig_programme_lifecycle"):
            raise ValidationError(_("Current-version status is controlled by the approval lifecycle."))
        return super().write(vals)

    def unlink(self):
        self._assert_mutable()
        return super().unlink()

    def action_submit_review(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only a draft programme version can be submitted for review."))
            record._validate_definition()
            record.with_context(hjig_programme_lifecycle=True).write({"state": "review"})

    def action_approve(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only a programme version under review can be approved."))
            user = self.env.user
            if not user.has_group("new_hongyijig_custom.group_hjig_document_controller"):
                raise UserError(_("Only a LaunchGuard Document Controller may approve a programme version."))
            if user not in record.template_id.approver_designation_id.holder_ids:
                raise UserError(_("You are not a current holder of the required approver designation."))
            if not record.effective_from:
                raise ValidationError(_("An effective-from date is required before approval."))
            record._validate_definition()
            record.template_id.version_ids.filtered(
                lambda version: version.id != record.id and version.is_current
            ).with_context(hjig_programme_lifecycle=True).write({"is_current": False})
            definition_hash = record._definition_hash()
            record.with_context(hjig_programme_lifecycle=True).write({
                "state": "approved",
                "is_current": True,
                "approved_by_id": user.id,
                "approved_on": fields.Datetime.now(),
                "definition_hash": definition_hash,
            })

    def _validate_definition(self):
        """Reject incomplete or internally inconsistent programme DNA before review/approval."""
        for record in self:
            if not record.gate_line_ids or not record.activity_line_ids:
                raise ValidationError(_("A programme version requires at least one gate and one activity."))
            if record.legacy_source_task_count and len(record.activity_line_ids) != record.legacy_source_task_count:
                raise ValidationError(
                    _("The activity count must reconcile exactly to the verified legacy source count.")
                )
            if record.dependency_review_status != "verified":
                raise ValidationError(_("The activity dependency map must be verified before review."))
            if record.evidence_review_status != "verified":
                raise ValidationError(_("The gate-by-gate SOP/Form map must be verified before review."))
            pending_content = record.activity_line_ids.filtered(
                lambda activity: "PENDING CHECKLIST CONTENT" in (activity.name or "").upper()
            )
            if pending_content:
                raise ValidationError(
                    _(
                        "This programme contains explicitly pending checklist content and cannot "
                        "enter governed review until that content is completed and verified."
                    )
                )
            sequences = record.gate_line_ids.mapped("sequence")
            if len(sequences) != len(set(sequences)):
                raise ValidationError(_("Gate sequences must be unique within a programme version."))
            empty_gates = record.gate_line_ids.filtered(
                lambda gate: gate.required and not record.activity_line_ids.filtered(
                    lambda activity: activity.gate_line_id == gate
                )
            )
            if empty_gates:
                raise ValidationError(_("Every required gate must contain at least one activity."))
            if len(record.activity_line_ids) > 1 and not record.activity_line_ids.mapped("predecessor_ids"):
                raise ValidationError(_("A multi-activity programme requires a verified dependency map."))
            if record.legacy_source_database and not record.dependency_rule_ids:
                raise ValidationError(_("Verified legacy programme DNA requires governed dependency-rule records."))
            unmapped_rules = record.dependency_rule_ids.filtered(
                lambda rule: not rule.predecessor_activity_id or not rule.successor_activity_id
            )
            if unmapped_rules:
                raise ValidationError(_("Every applicable dependency rule must map to both template activities."))
            ordered_required_gates = record.gate_line_ids.filtered("required").sorted("sequence")
            for gate in ordered_required_gates[1:]:
                gate_activities = record.activity_line_ids.filtered(lambda item: item.gate_line_id == gate)
                has_entry_dependency = any(
                    predecessor.gate_line_id.sequence < gate.sequence
                    for activity in gate_activities
                    for predecessor in activity.predecessor_ids
                )
                if not has_entry_dependency:
                    raise ValidationError(
                        _("Every required gate after the first must have an entry dependency from an earlier gate.")
                    )
            gate_stage_ids = set(record.gate_line_ids.mapped("stage_id").ids)
            if record.artifact_rule_ids.filtered(lambda rule: rule.stage_id.id not in gate_stage_ids):
                raise ValidationError(_("Every SOP/Form rule must belong to a gate in this programme version."))
            for gate in ordered_required_gates:
                if not record.artifact_rule_ids.filtered(
                    lambda rule: rule.stage_id == gate.stage_id and rule.mandatory
                ):
                    raise ValidationError(_("Every required gate needs at least one mandatory SOP/Form rule."))
            rule_keys = {
                (rule.stage_id.id, rule.artifact_master_id.id)
                for rule in record.artifact_rule_ids
            }
            for activity in record.activity_line_ids:
                missing = activity.required_artifact_ids.filtered(
                    lambda artifact: (activity.gate_line_id.stage_id.id, artifact.id) not in rule_keys
                )
                if missing:
                    raise ValidationError(
                        _("Activity %s requires SOPs/Forms that are not governed at its gate.") % activity.code
                    )
            record._check_dependency_cycles()

    def _check_dependency_cycles(self):
        for record in self:
            visiting = set()
            visited = set()

            def visit(activity):
                if activity.id in visiting:
                    raise ValidationError(_("The programme dependency map contains a cycle."))
                if activity.id in visited:
                    return
                visiting.add(activity.id)
                for predecessor in activity.predecessor_ids:
                    visit(predecessor)
                visiting.remove(activity.id)
                visited.add(activity.id)

            for activity in record.activity_line_ids:
                visit(activity)

    def action_retire(self):
        for record in self:
            if record.state != "approved":
                raise UserError(_("Only an approved programme version can be retired."))
            record.with_context(hjig_programme_lifecycle=True).write({
                "state": "retired", "is_current": False, "effective_to": fields.Date.today()
            })

    @api.constrains("state", "is_current", "template_id")
    def _check_current_version(self):
        for record in self:
            if record.is_current and record.state != "approved":
                raise ValidationError(_("Only an approved programme version can be current."))
            if record.is_current and self.search_count([
                ("template_id", "=", record.template_id.id),
                ("is_current", "=", True),
                ("id", "!=", record.id),
            ]):
                raise ValidationError(_("A programme can have only one current version."))

    def _definition_payload(self):
        self.ensure_one()
        gates = [
            {
                "code": line.stage_id.code,
                "sequence": line.sequence,
                "required": line.required,
                "closure_variant": line.closure_variant,
            }
            for line in self.gate_line_ids.sorted(lambda line: (line.sequence, line.id))
        ]
        activities = [
            {
                "code": line.code,
                "name": line.name,
                "sequence": line.sequence,
                "gate": line.gate_line_id.stage_id.code,
                "owner": line.owner_designation_id.code,
                "approver": line.approver_designation_id.code,
                "offset_days": line.offset_days,
                "duration_days": line.duration_days,
                "execution_basis": line.execution_basis,
                "conditional": line.conditional,
                "legacy_master_codes": line.legacy_master_codes,
                "predecessors": sorted(line.predecessor_ids.mapped("code")),
                "artifacts": sorted(line.required_artifact_ids.mapped("code")),
                "legacy_source_task_id": line.legacy_source_task_id,
                "legacy_source_stage_id": line.legacy_source_stage_id,
            }
            for line in self.activity_line_ids.sorted(lambda line: (line.sequence, line.id))
        ]
        artifacts = [
            {
                "code": line.artifact_master_id.code,
                "stage": line.stage_id.code,
                "mandatory": line.mandatory,
            }
            for line in self.artifact_rule_ids.sorted(lambda line: (line.stage_id.sequence, line.id))
        ]
        dependency_rules = [
            {
                "source_rule_id": line.legacy_source_rule_id,
                "predecessor": line.predecessor_activity_id.code,
                "successor": line.successor_activity_id.code,
                "predecessor_basis": line.predecessor_basis,
                "successor_basis": line.successor_basis,
                "rule_type": line.rule_type,
                "scope_matching_rule": line.scope_matching_rule,
                "aggregation_requirement": line.aggregation_requirement,
                "conditional_handling": line.conditional_handling,
                "source_reference": line.source_reference,
                "source_version": line.source_version,
            }
            for line in self.dependency_rule_ids.sorted(lambda line: (line.legacy_source_rule_id, line.id))
        ]
        return {
            "programme": self.template_id.code,
            "version": self.version,
            "effective_from": fields.Date.to_string(self.effective_from),
            "legacy_source": {
                "database": self.legacy_source_database,
                "project_id": self.legacy_source_project_id,
                "task_count": self.legacy_source_task_count,
            },
            "gates": gates,
            "activities": activities,
            "artifacts": artifacts,
            "dependency_rules": dependency_rules,
            "dependency_review_status": self.dependency_review_status,
            "evidence_review_status": self.evidence_review_status,
        }

    def _definition_hash(self):
        payload = json.dumps(self._definition_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProgrammeVersionChildMixin(models.AbstractModel):
    _name = "hjig.programme.version.child.mixin"
    _description = "Programme Version Child Immutability"

    def _version_from_values(self, vals):
        version_id = vals.get("version_id")
        return self.env["hjig.programme.template.version"].browse(version_id).exists()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            version = self._version_from_values(vals)
            if version and version.state in ("approved", "retired"):
                raise ValidationError(_("Approved programme content cannot be extended."))
        return super().create(vals_list)

    def write(self, vals):
        if self.mapped("version_id").filtered(lambda version: version.state in ("approved", "retired")):
            raise ValidationError(_("Approved programme content is immutable."))
        return super().write(vals)

    def unlink(self):
        if self.mapped("version_id").filtered(lambda version: version.state in ("approved", "retired")):
            raise ValidationError(_("Approved programme content cannot be deleted."))
        return super().unlink()


class HjigProgrammeTemplateGate(models.Model):
    _name = "hjig.programme.template.gate"
    _description = "Programme Template Gate"
    _inherit = "hjig.programme.version.child.mixin"
    _order = "sequence, id"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    sequence = fields.Integer(required=True, default=10)
    required = fields.Boolean(default=True)
    closure_variant = fields.Selection(
        [("standard", "Standard"), ("lite", "Lite"), ("not_applicable", "Not Applicable")],
        default="standard",
        required=True,
        help="Allows TG-10 and TG-10-LITE to coexist until the closure rule is formally approved.",
    )

    _version_stage_unique = models.Constraint(
        "UNIQUE(version_id, stage_id, closure_variant)",
        "A gate variant may appear only once in a programme version.",
    )


class HjigProgrammeTemplateActivity(models.Model):
    _name = "hjig.programme.template.activity"
    _description = "Programme Template Activity"
    _inherit = "hjig.programme.version.child.mixin"
    _order = "sequence, code"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    sequence = fields.Integer(required=True, default=10)
    gate_line_id = fields.Many2one(
        "hjig.programme.template.gate", required=True, ondelete="restrict", index=True
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    offset_days = fields.Integer(default=0)
    duration_days = fields.Integer(default=1)
    predecessor_ids = fields.Many2many(
        "hjig.programme.template.activity",
        "hjig_programme_activity_dependency_rel",
        "activity_id",
        "predecessor_id",
        string="Predecessors",
    )
    required_artifact_ids = fields.Many2many(
        "hjig.governance.artifact.master",
        "hjig_programme_activity_artifact_rel",
        "activity_id",
        "artifact_id",
        string="Required SOPs / Forms",
    )
    source_task_id = fields.Many2one(
        "project.task", string="Legacy Template Task", ondelete="restrict", copy=False
    )
    legacy_source_task_id = fields.Integer(readonly=True, copy=False, index=True)
    legacy_source_stage_id = fields.Integer(readonly=True, copy=False)
    legacy_source_stage_name = fields.Char(readonly=True, copy=False)
    legacy_master_codes = fields.Char(
        readonly=True,
        copy=False,
        index=True,
        help="Comma-separated Activity Master codes reconciled from the verified legacy task label.",
    )
    execution_basis = fields.Selection(
        [("project", "Project"), ("component", "Component"), ("mould", "Mould")],
        default="project",
        required=True,
    )
    conditional = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _version_code_unique = models.Constraint(
        "UNIQUE(version_id, code)",
        "Activity code must be unique within a programme version.",
    )
    _version_legacy_task_unique = models.Constraint(
        "UNIQUE(version_id, legacy_source_task_id)",
        "A legacy task may be reconciled only once in a programme version.",
    )

    @api.constrains("gate_line_id", "version_id", "predecessor_ids", "duration_days")
    def _check_activity_governance(self):
        for activity in self:
            if activity.gate_line_id.version_id != activity.version_id:
                raise ValidationError(_("The activity gate must belong to the same programme version."))
            if activity in activity.predecessor_ids:
                raise ValidationError(_("An activity cannot depend on itself."))
            if activity.predecessor_ids.filtered(lambda predecessor: predecessor.version_id != activity.version_id):
                raise ValidationError(_("Activity dependencies cannot cross programme versions."))
            if activity.predecessor_ids.filtered(lambda predecessor: predecessor.sequence >= activity.sequence):
                raise ValidationError(_("Every predecessor must have an earlier sequence than its dependent activity."))
            if activity.duration_days < 0:
                raise ValidationError(_("Activity duration cannot be negative."))
            if activity.owner_designation_id == activity.approver_designation_id:
                raise ValidationError(_("Activity owner and approver designations must be different."))


class HjigProgrammeTemplateDependencyRule(models.Model):
    _name = "hjig.programme.template.dependency.rule"
    _description = "Programme Template Scoped Dependency Rule"
    _inherit = "hjig.programme.version.child.mixin"
    _order = "legacy_source_rule_id, id"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    legacy_source_rule_id = fields.Integer(required=True, readonly=True, copy=False, index=True)
    predecessor_activity_id = fields.Many2one(
        "hjig.programme.template.activity", required=True, ondelete="restrict", index=True
    )
    successor_activity_id = fields.Many2one(
        "hjig.programme.template.activity", required=True, ondelete="restrict", index=True
    )
    predecessor_basis = fields.Selection(
        [("project", "Project"), ("component", "Component"), ("mould", "Mould")], required=True
    )
    successor_basis = fields.Selection(
        [("project", "Project"), ("component", "Component"), ("mould", "Mould")], required=True
    )
    rule_type = fields.Char(required=True)
    scope_matching_rule = fields.Char(required=True)
    aggregation_requirement = fields.Text(required=True)
    conditional_handling = fields.Text()
    source_reference = fields.Char()
    source_version = fields.Char()

    _version_source_rule_unique = models.Constraint(
        "UNIQUE(version_id, legacy_source_rule_id)",
        "A verified dependency rule may be reconciled only once per programme version.",
    )

    @api.constrains("version_id", "predecessor_activity_id", "successor_activity_id")
    def _check_rule_mapping(self):
        for rule in self:
            if rule.predecessor_activity_id.version_id != rule.version_id:
                raise ValidationError(_("Dependency predecessor must belong to the same programme version."))
            if rule.successor_activity_id.version_id != rule.version_id:
                raise ValidationError(_("Dependency successor must belong to the same programme version."))
            if rule.predecessor_activity_id == rule.successor_activity_id:
                raise ValidationError(_("A dependency rule cannot point an activity to itself."))


class HjigProgrammeTemplateArtifact(models.Model):
    _name = "hjig.programme.template.artifact"
    _description = "Programme Template Artifact Rule"
    _inherit = "hjig.programme.version.child.mixin"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    artifact_master_id = fields.Many2one(
        "hjig.governance.artifact.master", required=True, ondelete="restrict", index=True
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    mandatory = fields.Boolean(default=True)

    _version_artifact_stage_unique = models.Constraint(
        "UNIQUE(version_id, artifact_master_id, stage_id)",
        "An SOP/Form rule may appear only once per programme stage.",
    )

    @api.constrains("stage_id", "artifact_master_id", "version_id")
    def _check_artifact_stage(self):
        for rule in self:
            if rule.stage_id not in rule.artifact_master_id.applicable_stage_ids:
                raise ValidationError(_("The selected SOP/Form is not approved for this stage."))
            if rule.stage_id not in rule.version_id.gate_line_ids.mapped("stage_id"):
                raise ValidationError(_("The SOP/Form rule stage must exist in the programme version."))


class HjigProgrammeRun(models.Model):
    _name = "hjig.programme.run"
    _description = "Immutable Programme Run Snapshot"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "activated_on desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    sale_order_id = fields.Many2one(
        "sale.order", required=True, readonly=True, ondelete="restrict", index=True
    )
    project_id = fields.Many2one(
        "project.project", required=True, readonly=True, ondelete="restrict", index=True
    )
    template_version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, readonly=True, ondelete="restrict", index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("generated", "Generated"), ("closed", "Closed")],
        default="draft",
        required=True,
        tracking=True,
    )
    activated_on = fields.Datetime(readonly=True, copy=False)
    activated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    definition_hash = fields.Char(readonly=True, copy=False, index=True)
    snapshot_json = fields.Json(readonly=True, copy=False)
    task_ids = fields.One2many("project.task", "hjig_programme_run_id", readonly=True)
    artifact_requirement_ids = fields.One2many(
        "hjig.programme.run.artifact", "run_id", readonly=True
    )
    gate_ids = fields.One2many("hjig.programme.run.gate", "run_id", readonly=True)
    sourcebridge_engagement_ids = fields.One2many(
        "hjig.sourcebridge.engagement", "programme_run_id", string="SourceBridge Engagements"
    )
    portfolio_guard_id = fields.Many2one(
        "hjig.portfolio.guard", ondelete="restrict", index=True, tracking=True
    )

    _sale_order_unique = models.Constraint(
        "UNIQUE(sale_order_id)",
        "An Order Punch can activate only one programme run.",
    )
    _project_unique = models.Constraint(
        "UNIQUE(project_id)",
        "A project can have only one programme run.",
    )

    def write(self, vals):
        frozen = {
            "name", "sale_order_id", "project_id", "template_version_id", "activated_on",
            "activated_by_id", "definition_hash", "snapshot_json",
        }
        if frozen.intersection(vals) and self.filtered(lambda run: run.state in ("generated", "closed")):
            raise ValidationError(_("A generated programme-run snapshot is immutable."))
        if "state" in vals and not self.env.context.get("hjig_run_workflow"):
            raise ValidationError(_("Use the governed programme-run actions to change run state."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda run: run.state in ("generated", "closed")):
            raise UserError(_("A generated programme run cannot be deleted."))
        return super().unlink()

    def action_generate_execution(self):
        for run in self:
            if run.state == "generated":
                continue
            if run.template_version_id.state != "approved":
                raise ValidationError(_("Only an approved programme version can generate execution records."))
            version = run.template_version_id
            task_by_activity = {}
            for activity in version.activity_line_ids.sorted(lambda line: (line.sequence, line.id)):
                users = activity.owner_designation_id.holder_ids
                task = self.env["project.task"].create({
                    "name": activity.name,
                    "project_id": run.project_id.id,
                    "sequence": activity.sequence,
                    "user_ids": [(6, 0, users.ids)],
                    "hjig_programme_run_id": run.id,
                    "hjig_template_activity_id": activity.id,
                    "hjig_governance_stage_id": activity.gate_line_id.stage_id.id,
                    "hjig_owner_designation_id": activity.owner_designation_id.id,
                    "hjig_approver_designation_id": activity.approver_designation_id.id,
                })
                task_by_activity[activity.id] = task
            for activity in version.activity_line_ids:
                task = task_by_activity[activity.id]
                predecessors = self.env["project.task"].browse(
                    [task_by_activity[item.id].id for item in activity.predecessor_ids]
                )
                if predecessors:
                    task.depend_on_ids = [(6, 0, predecessors.ids)]
            for rule in version.artifact_rule_ids:
                self.env["hjig.programme.run.artifact"].create({
                    "run_id": run.id,
                    "artifact_master_id": rule.artifact_master_id.id,
                    "stage_id": rule.stage_id.id,
                    "mandatory": rule.mandatory,
                })
            for gate in version.gate_line_ids.sorted(lambda line: (line.sequence, line.id)):
                self.env["hjig.programme.run.gate"].create({
                    "run_id": run.id,
                    "template_gate_id": gate.id,
                    "stage_id": gate.stage_id.id,
                    "sequence": gate.sequence,
                    "required": gate.required,
                })
            payload = version._definition_payload()
            run.with_context(hjig_run_workflow=True).write({
                "state": "generated",
                "activated_on": fields.Datetime.now(),
                "activated_by_id": self.env.user.id,
                "definition_hash": version.definition_hash,
                "snapshot_json": payload,
            })
        return True

    def action_close_run(self):
        for run in self:
            if run.state != "generated":
                raise UserError(_("Only a generated programme run can be closed."))
            if run.gate_ids.filtered(lambda gate: gate.required and gate.state != "approved"):
                raise ValidationError(_("All required programme gates must be approved before closure."))
            if run.artifact_requirement_ids.filtered(
                lambda item: item.mandatory and item.status != "approved"
            ):
                raise ValidationError(_("All mandatory SOP/Form evidence must be approved before closure."))
            run.with_context(hjig_run_workflow=True).write({"state": "closed"})


class HjigProgrammeRunGate(models.Model):
    _name = "hjig.programme.run.gate"
    _description = "Programme Run Gate Control"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "run_id, sequence, id"

    run_id = fields.Many2one("hjig.programme.run", required=True, ondelete="cascade", index=True)
    template_gate_id = fields.Many2one(
        "hjig.programme.template.gate", required=True, readonly=True, ondelete="restrict"
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, readonly=True, ondelete="restrict", index=True
    )
    sequence = fields.Integer(required=True, readonly=True)
    required = fields.Boolean(default=True, readonly=True)
    state = fields.Selection(
        [("blocked", "Blocked"), ("ready", "Ready"), ("approved", "Approved")],
        default="blocked",
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    approval_note = fields.Text(tracking=True)

    _run_gate_unique = models.Constraint(
        "UNIQUE(run_id, template_gate_id)",
        "A programme gate can appear only once in a programme run.",
    )

    def _blocking_reasons(self):
        self.ensure_one()
        reasons = []
        earlier = self.run_id.gate_ids.filtered(
            lambda gate: gate.required and gate.sequence < self.sequence and gate.state != "approved"
        )
        if earlier:
            reasons.append(_("earlier required gates are not approved"))
        tasks = self.run_id.task_ids.filtered(lambda task: task.hjig_governance_stage_id == self.stage_id)
        if tasks.filtered(lambda task: not task.stage_id.fold):
            reasons.append(_("gate activities are not complete"))
        artifacts = self.run_id.artifact_requirement_ids.filtered(
            lambda item: item.stage_id == self.stage_id and item.mandatory
        )
        if artifacts.filtered(lambda item: item.status != "approved"):
            reasons.append(_("mandatory SOP/Form evidence is not approved"))
        return reasons

    def action_refresh_readiness(self):
        for gate in self.filtered(lambda item: item.state != "approved"):
            gate.with_context(hjig_gate_workflow=True).write({
                "state": "blocked" if gate._blocking_reasons() else "ready"
            })
        return True

    def action_approve_gate(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_document_controller"):
            raise UserError(_("Only an authorised Document Controller may approve a programme gate."))
        for gate in self:
            gate.action_refresh_readiness()
            if gate.state != "ready":
                raise ValidationError(_("Gate cannot close: %s.") % ", ".join(gate._blocking_reasons()))
            approvers = gate.run_id.template_version_id.template_id.approver_designation_id.holder_ids
            if self.env.user not in approvers:
                raise UserError(_("You do not hold the required programme approver designation."))
            gate.with_context(hjig_gate_workflow=True).write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
            })
        return True

    def write(self, vals):
        frozen = {"run_id", "template_gate_id", "stage_id", "sequence", "required"}
        if frozen.intersection(vals):
            raise ValidationError(_("Generated gate identity is immutable."))
        if "state" in vals and not self.env.context.get("hjig_gate_workflow"):
            raise ValidationError(_("Use the governed gate actions to change gate state."))
        if self.filtered(lambda gate: gate.state == "approved") and set(vals) - {"message_follower_ids"}:
            raise ValidationError(_("An approved gate is immutable."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Generated programme gates cannot be deleted."))


class HjigProgrammeRunArtifact(models.Model):
    _name = "hjig.programme.run.artifact"
    _description = "Programme Run SOP/Form Requirement"
    _order = "stage_id, artifact_master_id"

    run_id = fields.Many2one("hjig.programme.run", required=True, ondelete="cascade", index=True)
    artifact_master_id = fields.Many2one(
        "hjig.governance.artifact.master", required=True, ondelete="restrict", index=True
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    mandatory = fields.Boolean(default=True, readonly=True)
    status = fields.Selection(
        [("required", "Required"), ("available", "Available"), ("approved", "Approved")],
        compute="_compute_status",
        store=True,
    )
    project_document_id = fields.Many2one("hjig.project.document", ondelete="restrict")

    _run_artifact_stage_unique = models.Constraint(
        "UNIQUE(run_id, artifact_master_id, stage_id)",
        "A programme-run SOP/Form requirement may appear only once per stage.",
    )

    @api.depends("project_document_id", "project_document_id.status")
    def _compute_status(self):
        for requirement in self:
            document = requirement.project_document_id
            requirement.status = (
                "approved" if document and document.status == "approved"
                else "available" if document else "required"
            )

    @api.constrains("project_document_id")
    def _check_project_document(self):
        for requirement in self.filtered("project_document_id"):
            document = requirement.project_document_id
            if document.project_id != requirement.run_id.project_id:
                raise ValidationError(_("The controlled document must belong to the programme-run project."))
            if document.artifact_master_id != requirement.artifact_master_id:
                raise ValidationError(_("The controlled document does not satisfy this SOP/Form requirement."))
            if document.stage_id != requirement.stage_id:
                raise ValidationError(_("The controlled document is registered against a different gate."))


class HjigPortfolioGuard(models.Model):
    _name = "hjig.portfolio.guard"
    _description = "PortfolioGuard Retainership"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True, index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    sale_order_id = fields.Many2one("sale.order", ondelete="restrict", tracking=True)
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    programme_run_ids = fields.One2many("hjig.programme.run", "portfolio_guard_id")
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("owner_designation_id", "approver_designation_id", "programme_run_ids", "partner_id")
    def _check_portfolio_governance(self):
        for portfolio in self:
            if portfolio.owner_designation_id == portfolio.approver_designation_id:
                raise ValidationError(_("PortfolioGuard owner and approver designations must differ."))
            wrong_customer = portfolio.programme_run_ids.filtered(
                lambda run: run.project_id.partner_id.commercial_partner_id
                != portfolio.partner_id.commercial_partner_id
            )
            if wrong_customer:
                raise ValidationError(_("All PortfolioGuard projects must belong to the same customer."))

    def action_activate(self):
        for portfolio in self:
            if portfolio.state != "draft":
                raise UserError(_("Only a Draft PortfolioGuard retainership can be activated."))
            if len(portfolio.programme_run_ids) < 2:
                raise ValidationError(_("PortfolioGuard requires at least two governed project programme runs."))
            if self.env.user not in portfolio.approver_designation_id.holder_ids:
                raise UserError(_("You do not hold the PortfolioGuard approver designation."))
            portfolio.with_context(hjig_portfolio_workflow=True).write({"state": "active"})

    def action_close(self):
        for portfolio in self:
            if portfolio.state != "active":
                raise UserError(_("Only an Active PortfolioGuard retainership can be closed."))
            if portfolio.programme_run_ids.filtered(lambda run: run.state != "closed"):
                raise ValidationError(_("All PortfolioGuard programme runs must be closed first."))
            portfolio.with_context(hjig_portfolio_workflow=True).write({"state": "closed"})

    def write(self, vals):
        if "state" in vals and not self.env.context.get("hjig_portfolio_workflow"):
            raise ValidationError(_("Use the governed PortfolioGuard workflow actions."))
        frozen = {"partner_id", "sale_order_id", "owner_designation_id", "approver_designation_id"}
        if frozen.intersection(vals) and self.filtered(lambda item: item.state in ("active", "closed")):
            raise ValidationError(_("Active PortfolioGuard governance fields are frozen."))
        return super().write(vals)


class HjigSourcebridgeEngagement(models.Model):
    _name = "hjig.sourcebridge.engagement"
    _description = "SourceBridge Engagement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, code"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True)
    programme_run_id = fields.Many2one(
        "hjig.programme.run", required=True, ondelete="restrict", index=True, tracking=True
    )
    sale_order_id = fields.Many2one("sale.order", ondelete="restrict", tracking=True)
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    component_ids = fields.One2many("hjig.sourcebridge.component", "engagement_id")
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "SourceBridge engagement code must be unique.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    @api.constrains("project_id", "programme_run_id", "owner_designation_id", "approver_designation_id")
    def _check_engagement_governance(self):
        for engagement in self:
            if engagement.programme_run_id.project_id != engagement.project_id:
                raise ValidationError(_("SourceBridge must link to the programme run of the same project."))
            if engagement.owner_designation_id == engagement.approver_designation_id:
                raise ValidationError(_("SourceBridge owner and approver designations must differ."))

    def action_activate(self):
        for engagement in self:
            if engagement.state != "draft":
                raise UserError(_("Only a Draft SourceBridge engagement can be activated."))
            if not engagement.component_ids:
                raise ValidationError(_("SourceBridge requires at least one sourcing component."))
            if self.env.user not in engagement.approver_designation_id.holder_ids:
                raise UserError(_("You do not hold the SourceBridge approver designation."))
            engagement.with_context(hjig_sourcebridge_workflow=True).write({"state": "active"})

    def action_close(self):
        for engagement in self:
            if engagement.state != "active":
                raise UserError(_("Only an Active SourceBridge engagement can be closed."))
            if engagement.component_ids.filtered(lambda component: component.status != "accepted"):
                raise ValidationError(_("Every SourceBridge component must be accepted before closure."))
            engagement.with_context(hjig_sourcebridge_workflow=True).write({"state": "closed"})

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        if "state" in vals and not self.env.context.get("hjig_sourcebridge_workflow"):
            raise ValidationError(_("Use the governed SourceBridge workflow actions."))
        frozen = {
            "code", "project_id", "programme_run_id", "sale_order_id",
            "owner_designation_id", "approver_designation_id",
        }
        if frozen.intersection(vals) and self.filtered(lambda item: item.state in ("active", "closed")):
            raise ValidationError(_("Active SourceBridge governance fields are frozen."))
        return super().write(vals)


class HjigSourcebridgeComponent(models.Model):
    _name = "hjig.sourcebridge.component"
    _description = "SourceBridge Sourcing Component"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "engagement_id, sequence, code"

    engagement_id = fields.Many2one(
        "hjig.sourcebridge.engagement", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10, required=True)
    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    category = fields.Selection(
        [
            ("tooling", "Tooling / Mould"),
            ("plastic", "Plastic Component"),
            ("metal", "Metal Component"),
            ("bought_out", "Bought-out Component"),
            ("material", "Raw Material"),
            ("service", "Special Process / Service"),
            ("other", "Other"),
        ],
        required=True,
        tracking=True,
    )
    quantity = fields.Float(default=1.0, required=True)
    specification = fields.Text(required=True)
    status = fields.Selection(
        [
            ("identified", "Identified"),
            ("rfq", "RFQ"),
            ("nominated", "Supplier Nominated"),
            ("sample", "Sample / Validation"),
            ("accepted", "Accepted"),
        ],
        default="identified",
        required=True,
        tracking=True,
    )

    _engagement_code_unique = models.Constraint(
        "UNIQUE(engagement_id, code)",
        "SourceBridge component code must be unique within an engagement.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
            engagement = self.env["hjig.sourcebridge.engagement"].browse(
                vals.get("engagement_id")
            ).exists()
            if engagement and engagement.state != "draft":
                raise ValidationError(_("Components may be added only while SourceBridge is Draft."))
        return super().create(vals_list)

    @api.constrains("quantity")
    def _check_quantity(self):
        if self.filtered(lambda item: item.quantity <= 0):
            raise ValidationError(_("SourceBridge component quantity must be greater than zero."))

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        identity = {"engagement_id", "code", "name", "category", "quantity", "specification"}
        if identity.intersection(vals) and self.mapped("engagement_id").filtered(
            lambda engagement: engagement.state != "draft"
        ):
            raise ValidationError(_("Active SourceBridge component identity is frozen."))
        if vals.get("status") == "accepted" and not self.env.context.get("hjig_component_accept"):
            raise ValidationError(_("Use the governed Accept action for a SourceBridge component."))
        return super().write(vals)

    def action_accept(self):
        for component in self:
            engagement = component.engagement_id
            if engagement.state != "active":
                raise ValidationError(_("The SourceBridge engagement must be Active."))
            if self.env.user not in engagement.approver_designation_id.holder_ids:
                raise UserError(_("You do not hold the SourceBridge approver designation."))
            component.with_context(hjig_component_accept=True).write({"status": "accepted"})
        return True

    def unlink(self):
        if self.mapped("engagement_id").filtered(lambda engagement: engagement.state != "draft"):
            raise UserError(_("Active SourceBridge components cannot be deleted."))
        return super().unlink()


class SaleOrder(models.Model):
    _inherit = "sale.order"

    hjig_programme_version_id = fields.Many2one(
        "hjig.programme.template.version",
        string="Approved Programme Version",
        domain="[('state', '=', 'approved'), ('is_current', '=', True)]",
        tracking=True,
        copy=False,
    )
    hjig_project_code = fields.Char(
        string="Governed Project Code",
        copy=False,
        tracking=True,
        help="Approved code to assign when this Order Punch activates the customer project.",
    )
    hjig_project_id = fields.Many2one("project.project", copy=False, readonly=True, tracking=True)
    hjig_programme_run_id = fields.Many2one("hjig.programme.run", copy=False, readonly=True)
    hjig_order_punch_pdf_url = fields.Char(string="Approved Order Punch PDF", copy=False, tracking=True)
    hjig_commercial_pdf_url = fields.Char(string="Approved Commercial PDF", copy=False, tracking=True)

    def write(self, vals):
        governed = {
            "hjig_programme_version_id", "hjig_project_code", "hjig_project_id", "hjig_programme_run_id",
            "hjig_order_punch_pdf_url", "hjig_commercial_pdf_url",
        }
        if governed.intersection(vals) and self.filtered("hjig_programme_run_id"):
            if not self.env.context.get("hjig_programme_activation"):
                raise ValidationError(_("Order Punch programme selection is frozen after activation."))
        return super().write(vals)

    def action_activate_hjig_programme(self):
        self.ensure_one()
        existing = self.env["hjig.programme.run"].search([("sale_order_id", "=", self.id)], limit=1)
        if existing:
            return self._hjig_run_action(existing)
        if self.state not in ("sale", "done"):
            raise UserError(_("The Order Punch must be confirmed before programme activation."))
        version = self.hjig_programme_version_id
        if not version or version.state != "approved" or not version.is_current:
            raise ValidationError(_("Select the current approved programme version before activation."))
        project_code = (self.hjig_project_code or "").strip().upper()
        if not project_code:
            raise ValidationError(_("Enter the approved governed project code before activation."))
        code_parts = project_code.split("-")
        if len(code_parts) != 4 or code_parts[1] != version.template_id.code:
            raise ValidationError(
                _("The Project Code programme segment must match the selected programme template (%s).")
                % version.template_id.code
            )
        approved_pdf_prefixes = ("https://drive.google.com/", "https://docs.google.com/")
        if not (self.hjig_order_punch_pdf_url or "").strip().startswith(approved_pdf_prefixes):
            raise ValidationError(_("Link the approved Order Punch PDF before programme activation."))
        if not (self.hjig_commercial_pdf_url or "").strip().startswith(approved_pdf_prefixes):
            raise ValidationError(_("Link the approved Commercial PDF before programme activation."))
        project = self.hjig_project_id
        if not project:
            project_values = {
                "name": "%s - %s" % (self.partner_id.name, version.template_id.name),
                "partner_id": self.partner_id.id,
                "company_id": self.company_id.id,
                "hjig_project_record_type": "customer",
                "x_project_code": project_code,
            }
            project_fields = self.env["project.project"]._fields
            if "x_order_reference_id" in project_fields:
                project_values["x_order_reference_id"] = self.id
            project = self.env["project.project"].create(project_values)
        run = self.env["hjig.programme.run"].create({
            "name": "%s / %s" % (project.x_project_code, version.name),
            "sale_order_id": self.id,
            "project_id": project.id,
            "template_version_id": version.id,
        })
        self.with_context(hjig_programme_activation=True).write({
            "hjig_project_id": project.id, "hjig_programme_run_id": run.id
        })
        run.action_generate_execution()
        return self._hjig_run_action(run)

    def _hjig_run_action(self, run):
        return {
            "type": "ir.actions.act_window",
            "name": _("Programme Run"),
            "res_model": "hjig.programme.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_programme_run_ids = fields.One2many("hjig.programme.run", "project_id")
    hjig_programme_run_count = fields.Integer(compute="_compute_hjig_programme_run_count")
    sourcebridge_engagement_ids = fields.One2many(
        "hjig.sourcebridge.engagement", "project_id", string="SourceBridge Engagements"
    )

    @api.depends("hjig_programme_run_ids")
    def _compute_hjig_programme_run_count(self):
        for project in self:
            project.hjig_programme_run_count = len(project.hjig_programme_run_ids)


class ProjectTask(models.Model):
    _inherit = "project.task"

    hjig_programme_run_id = fields.Many2one(
        "hjig.programme.run", readonly=True, ondelete="restrict", index=True, copy=False
    )
    hjig_template_activity_id = fields.Many2one(
        "hjig.programme.template.activity", readonly=True, ondelete="restrict", index=True, copy=False
    )
    hjig_governance_stage_id = fields.Many2one(
        "hjig.launchguard.stage", ondelete="restrict", index=True, tracking=True
    )
    hjig_owner_designation_id = fields.Many2one(
        "hjig.governance.designation", ondelete="restrict", index=True, tracking=True
    )
    hjig_approver_designation_id = fields.Many2one(
        "hjig.governance.designation", ondelete="restrict", index=True, tracking=True
    )

    _programme_activity_unique = models.Constraint(
        "UNIQUE(hjig_programme_run_id, hjig_template_activity_id)",
        "A programme activity can generate only one task in a programme run.",
    )

    def write(self, vals):
        frozen = {
            "hjig_programme_run_id", "hjig_template_activity_id", "hjig_governance_stage_id",
            "hjig_owner_designation_id", "hjig_approver_designation_id",
        }
        if frozen.intersection(vals) and self.filtered(
            lambda task: task.hjig_programme_run_id.state in ("generated", "closed")
        ):
            raise ValidationError(_("Generated task governance fields are frozen by the programme snapshot."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda task: task.hjig_programme_run_id.state in ("generated", "closed")):
            raise UserError(_("A generated programme activity task cannot be deleted."))
        return super().unlink()
