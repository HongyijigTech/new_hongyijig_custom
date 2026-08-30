# -*- coding: utf-8 -*-
import hashlib
import json
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


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
    checklist_item_ids = fields.One2many(
        "hjig.programme.template.checklist.item", "version_id"
    )
    dependency_review_status = fields.Selection(
        [("unreviewed", "Unreviewed"), ("verified", "Verified")],
        required=True,
        default="unreviewed",
        tracking=True,
        help="A verified status means the activity dependency map was reviewed against the approved programme DNA.",
    )
    dependency_review_evidence = fields.Char(
        string="Dependency Review Evidence", tracking=True,
        help="Controlled document reference, Drive URL, or immutable export hash used for this verification.",
    )
    dependency_reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    dependency_reviewed_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    evidence_review_status = fields.Selection(
        [("unreviewed", "Unreviewed"), ("verified", "Verified")],
        required=True,
        default="unreviewed",
        tracking=True,
        help="A verified status means every mandatory SOP/Form requirement was reviewed gate by gate.",
    )
    evidence_review_evidence = fields.Char(
        string="Evidence-Map Review Evidence", tracking=True,
        help="Controlled document reference, Drive URL, or immutable export hash used for this verification.",
    )
    evidence_reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    evidence_reviewed_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    timing_review_status = fields.Selection(
        [("unreviewed", "Unreviewed"), ("verified", "Verified")],
        required=True,
        default="unreviewed",
        tracking=True,
        help=(
            "A verified status means every activity duration and planning offset was approved "
            "as an internal planning baseline. It is not a customer delivery commitment."
        ),
    )
    timing_review_evidence = fields.Char(
        string="Timing Review Evidence", tracking=True,
        help="Controlled baseline reference or approval record supporting every internal planning duration.",
    )
    timing_reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    timing_reviewed_on = fields.Datetime(readonly=True, copy=False, tracking=True)
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

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.context.get("hjig_programme_review_control") or self.env.is_superuser()):
            for vals in vals_list:
                if any(vals.get(field_name) == "verified" for field_name in (
                    "dependency_review_status", "evidence_review_status", "timing_review_status",
                )):
                    raise ValidationError(_("A new programme version must begin with Unreviewed review controls."))
        return super().create(vals_list)

    def _assert_mutable(self):
        if self.filtered(lambda record: record.state != "draft"):
            raise ValidationError(
                _("Only a Draft programme version may be edited. Review, Approved and Retired versions are immutable.")
            )

    def write(self, vals):
        governed = {
            "template_id", "version", "effective_from", "effective_to", "source_project_id",
            "legacy_source_database", "legacy_source_project_id", "legacy_source_task_count",
            "gate_line_ids", "activity_line_ids", "artifact_rule_ids",
            "dependency_rule_ids", "checklist_item_ids",
            "dependency_review_status", "evidence_review_status", "timing_review_status",
            "dependency_review_evidence", "evidence_review_evidence", "timing_review_evidence",
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
        review_controlled = {
            "dependency_review_status", "dependency_reviewed_by_id", "dependency_reviewed_on",
            "evidence_review_status", "evidence_reviewed_by_id", "evidence_reviewed_on",
            "timing_review_status", "timing_reviewed_by_id", "timing_reviewed_on",
        }
        if review_controlled.intersection(vals) and not (
            self.env.context.get("hjig_programme_review_control") or self.env.is_superuser()
        ):
            raise ValidationError(_("Use the governed verification actions to change review status."))
        result = super().write(vals)
        review_invalidating = {
            "template_id", "version", "source_project_id", "legacy_source_database",
            "legacy_source_project_id", "legacy_source_task_count", "gate_line_ids",
            "activity_line_ids", "artifact_rule_ids", "dependency_rule_ids", "checklist_item_ids",
            "dependency_review_evidence", "evidence_review_evidence", "timing_review_evidence",
        }
        if review_invalidating.intersection(vals) and not self.env.context.get("hjig_programme_review_control"):
            reviewed = self.filtered(
                lambda record: record.state == "draft" and (
                    record.dependency_reviewed_by_id
                    or record.evidence_reviewed_by_id
                    or record.timing_reviewed_by_id
                )
            )
            if reviewed:
                reviewed.with_context(hjig_programme_review_control=True).write({
                    "dependency_review_status": "unreviewed",
                    "dependency_reviewed_by_id": False,
                    "dependency_reviewed_on": False,
                    "evidence_review_status": "unreviewed",
                    "evidence_reviewed_by_id": False,
                    "evidence_reviewed_on": False,
                    "timing_review_status": "unreviewed",
                    "timing_reviewed_by_id": False,
                    "timing_reviewed_on": False,
                })
        return result

    def _assert_review_authority(self):
        self.ensure_one()
        user = self.env.user
        if not user.has_group("new_hongyijig_custom.group_hjig_document_controller"):
            raise UserError(_("Only a LaunchGuard Document Controller may verify a programme review."))
        if user not in self.template_id.approver_designation_id.holder_ids:
            raise UserError(_("You are not a current holder of the required programme approver designation."))
        if self.state != "draft":
            raise UserError(_("Reviews can be verified only while the programme version is Draft."))

    def _verify_review(self, review_kind):
        field_map = {
            "dependency": ("dependency_review_status", "dependency_review_evidence", "dependency_reviewed_by_id", "dependency_reviewed_on"),
            "evidence": ("evidence_review_status", "evidence_review_evidence", "evidence_reviewed_by_id", "evidence_reviewed_on"),
            "timing": ("timing_review_status", "timing_review_evidence", "timing_reviewed_by_id", "timing_reviewed_on"),
        }
        for record in self:
            record._assert_review_authority()
            status_field, evidence_field, reviewer_field, reviewed_on_field = field_map[review_kind]
            if not (record[evidence_field] or "").strip():
                raise ValidationError(_("A controlled evidence reference is required before verification."))
            if review_kind == "dependency":
                if record.legacy_source_database and not record.dependency_rule_ids:
                    raise ValidationError(_("Legacy programme DNA requires governed dependency-rule records."))
                if record.dependency_rule_ids.filtered(lambda rule: not rule.predecessor_activity_id or not rule.successor_activity_id):
                    raise ValidationError(_("Every dependency rule must map to both template activities."))
                if len(record.activity_line_ids) > 1 and not record.activity_line_ids.mapped("predecessor_ids"):
                    raise ValidationError(_("A multi-activity programme requires a dependency map."))
            elif review_kind == "evidence":
                missing_artifact = record.checklist_item_ids.filtered(
                    lambda item: item.mandatory and item.evidence_required and not item.evidence_artifact_id
                )
                if missing_artifact:
                    raise ValidationError(_("Every mandatory evidence checklist item requires a controlled artifact."))
                uncontrolled_commercial = record.activity_line_ids.filtered(
                    lambda item: re.match(r"^CM-\d{2}:", (item.name or "").upper())
                    and not item.commercial_control_required
                )
                if uncontrolled_commercial:
                    raise ValidationError(_("Every CM activity requires an explicit commercial milestone control."))
            else:
                if record.activity_line_ids.filtered(lambda activity: activity.duration_days <= 0):
                    raise ValidationError(_("Every activity requires a positive internal planning duration."))
            record.with_context(hjig_programme_review_control=True).write({
                status_field: "verified", reviewer_field: self.env.user.id,
                reviewed_on_field: fields.Datetime.now(),
            })
        return True

    def action_verify_dependency_review(self):
        return self._verify_review("dependency")

    def action_verify_evidence_review(self):
        return self._verify_review("evidence")

    def action_verify_timing_review(self):
        return self._verify_review("timing")

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
            reconciled_legacy_count = len(record.activity_line_ids.filtered("legacy_source_task_id"))
            if record.legacy_source_task_count and reconciled_legacy_count != record.legacy_source_task_count:
                raise ValidationError(
                    _("The activity count must reconcile exactly to the verified legacy source count.")
                )
            if record.dependency_review_status != "verified":
                raise ValidationError(_("The activity dependency map must be verified before review."))
            if record.evidence_review_status != "verified":
                raise ValidationError(_("The gate-by-gate SOP/Form map must be verified before review."))
            if record.timing_review_status != "verified":
                raise ValidationError(_("The activity timing baseline must be verified before review."))
            unbaselined = record.activity_line_ids.filtered(lambda activity: activity.duration_days <= 0)
            if unbaselined:
                raise ValidationError(
                    _("Every activity requires an approved positive planning duration before review.")
                )
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
            uncontrolled_commercial = record.activity_line_ids.filtered(
                lambda activity: re.match(r"^CM-\d{2}:", (activity.name or "").upper())
                and not activity.commercial_control_required
            )
            if uncontrolled_commercial:
                raise ValidationError(_("Every CM activity requires an explicit commercial milestone control."))
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
                if not record.checklist_item_ids.filtered(
                    lambda item: item.gate_line_id == gate and item.mandatory
                ):
                    raise ValidationError(
                        _("Every required gate needs at least one authoritative mandatory checklist item.")
                    )
                untyped_evidence = record.checklist_item_ids.filtered(
                    lambda item: item.gate_line_id == gate
                    and item.evidence_required
                    and not item.evidence_artifact_id
                )
                if untyped_evidence:
                    raise ValidationError(
                        _("Every evidence-required checklist item must specify its controlled SOP/Form type before review.")
                    )
                if gate.execution_basis == "mould" and not record.checklist_item_ids.filtered(
                    lambda item: item.gate_line_id == gate
                    and item.mandatory
                    and item.execution_basis == "mould"
                ):
                    raise ValidationError(
                        _("Every mould-basis gate needs an authoritative mandatory per-mould checklist item.")
                    )
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
                "coordinator": line.coordinator_designation_id.code,
                "support_designations": sorted(line.support_designation_ids.mapped("code")),
                "authority_source_reference": line.authority_source_reference,
                "authority_source_version": line.authority_source_version,
                "offset_days": line.offset_days,
                "duration_days": line.duration_days,
                "execution_basis": line.execution_basis,
                "conditional": line.conditional,
                "commercial_control_required": line.commercial_control_required,
                "commercial_customer_record_min": line.commercial_customer_record_min,
                "commercial_supplier_record_min": line.commercial_supplier_record_min,
                "commercial_no_impact_allowed": line.commercial_no_impact_allowed,
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
        checklist = [
            {
                "code": item.code,
                "gate": item.gate_line_id.stage_id.code,
                "sequence": item.sequence,
                "subhead": item.subhead,
                "text": item.item_text,
                "mandatory": item.mandatory,
                "conditional": item.conditional,
                "evidence_required": item.evidence_required,
                "sign_required": item.sign_required,
                "execution_basis": item.execution_basis,
                "linked_activity": item.linked_activity_id.code,
                "evidence_artifact": item.evidence_artifact_id.code,
                "owner": item.owner_designation_id.code,
                "approver": item.approver_designation_id.code,
                "auto_na_risk_below": item.auto_na_risk_below,
                "source_reference": item.source_reference,
                "source_version": item.source_version,
            }
            for item in self.checklist_item_ids.sorted(
                lambda item: (item.gate_line_id.sequence, item.sequence, item.id)
            )
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
            "checklist": checklist,
            "dependency_review_status": self.dependency_review_status,
            "evidence_review_status": self.evidence_review_status,
            "timing_review_status": self.timing_review_status,
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

    def _invalidate_version_reviews(self, versions):
        versions = versions.filtered(
            lambda version: version.state == "draft" and (
                version.dependency_reviewed_by_id
                or version.evidence_reviewed_by_id
                or version.timing_reviewed_by_id
            )
        )
        if versions:
            versions.with_context(hjig_programme_review_control=True).write({
                "dependency_review_status": "unreviewed",
                "dependency_reviewed_by_id": False,
                "dependency_reviewed_on": False,
                "evidence_review_status": "unreviewed",
                "evidence_reviewed_by_id": False,
                "evidence_reviewed_on": False,
                "timing_review_status": "unreviewed",
                "timing_reviewed_by_id": False,
                "timing_reviewed_on": False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            version = self._version_from_values(vals)
            if version and version.state != "draft":
                raise ValidationError(_("Only Draft programme content can be extended."))
        records = super().create(vals_list)
        records._invalidate_version_reviews(records.mapped("version_id"))
        return records

    def write(self, vals):
        if self.mapped("version_id").filtered(lambda version: version.state != "draft"):
            raise ValidationError(_("Only Draft programme content can be edited."))
        result = super().write(vals)
        self._invalidate_version_reviews(self.mapped("version_id"))
        return result

    def unlink(self):
        if self.mapped("version_id").filtered(lambda version: version.state != "draft"):
            raise ValidationError(_("Only Draft programme content can be deleted."))
        versions = self.mapped("version_id")
        result = super().unlink()
        self._invalidate_version_reviews(versions)
        return result


class HjigProgrammeTemplateGate(models.Model):
    _name = "hjig.programme.template.gate"
    _description = "Programme Template Gate"
    _inherit = "hjig.programme.version.child.mixin"
    _rec_name = "stage_id"
    _order = "sequence, id"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    stage_type = fields.Selection(related="stage_id.stage_type", store=True, readonly=True)
    sequence = fields.Integer(required=True, default=10)
    required = fields.Boolean(default=True)
    closure_variant = fields.Selection(
        [("standard", "Standard"), ("lite", "Lite"), ("not_applicable", "Not Applicable")],
        default="standard",
        required=True,
        help="Allows TG-10 and TG-10-LITE to coexist until the closure rule is formally approved.",
    )
    execution_basis = fields.Selection(
        [("project", "Project"), ("mould", "Mould")],
        required=True,
        default="project",
        help="Mould-basis gates close independently for each approved mould plan.",
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
    coordinator_designation_id = fields.Many2one(
        "hjig.governance.designation",
        ondelete="restrict",
        help="Project-movement coordinator; this does not replace the accountable activity owner.",
    )
    support_designation_ids = fields.Many2many(
        "hjig.governance.designation",
        "hjig_programme_activity_support_designation_rel",
        "activity_id",
        "designation_id",
        string="Supporting Designations",
        help="Additional controlled roles required to support the accountable owner.",
    )
    authority_source_reference = fields.Char(readonly=True, copy=False)
    authority_source_version = fields.Char(readonly=True, copy=False)
    offset_days = fields.Integer(default=0)
    duration_days = fields.Integer(
        default=1,
        help=(
            "Approved internal planning duration in working days. Zero means not yet baselined; "
            "it must never be interpreted as a customer commitment."
        ),
    )
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
    commercial_control_required = fields.Boolean(
        default=False,
        help="Requires a separately approved commercial milestone control before the gate can close.",
    )
    commercial_customer_record_min = fields.Integer(
        default=0,
        help="Minimum number of existing Verified customer commercial records required for this activity.",
    )
    commercial_supplier_record_min = fields.Integer(
        default=0,
        help="Minimum number of existing Verified supplier commercial records required for this activity.",
    )
    commercial_no_impact_allowed = fields.Boolean(
        default=False,
        help="Allows an independently approved No Commercial Impact decision instead of ledger records.",
    )
    active = fields.Boolean(default=True)

    _version_code_unique = models.Constraint(
        "UNIQUE(version_id, code)",
        "Activity code must be unique within a programme version.",
    )
    _version_legacy_task_unique = models.Constraint(
        "UNIQUE(version_id, legacy_source_task_id)",
        "A legacy task may be reconciled only once in a programme version.",
    )

    def _hjig_commercial_rule_defaults(self):
        """Return the conservative ledger-control profile for a named CM activity."""
        self.ensure_one()
        name = (self.name or "").upper()
        if not re.match(r"^CM-\d{2}:", name):
            return {
                "commercial_control_required": False,
                "commercial_customer_record_min": 0,
                "commercial_supplier_record_min": 0,
                "commercial_no_impact_allowed": False,
            }
        customer_min = supplier_min = 0
        no_impact_allowed = False
        milestone = name[:5]
        if milestone in ("CM-01", "CM-02", "CM-05", "CM-08"):
            customer_min = 1
        elif milestone == "CM-03":
            supplier_min = 2  # approved PO plus the actual payment record
        elif milestone in ("CM-04", "CM-09", "CM-11"):
            supplier_min = 1
        elif milestone == "CM-06":
            customer_min = supplier_min = 1
        elif milestone == "CM-07":
            customer_min = 1
            supplier_min = 0 if "DEMAND RAISED" in name else 1
        elif milestone == "CM-10":
            supplier_min = 1
            no_impact_allowed = True
        else:
            raise ValidationError(_("Commercial milestone %s has no controlled ledger profile.") % milestone)
        return {
            "commercial_control_required": True,
            "commercial_customer_record_min": customer_min,
            "commercial_supplier_record_min": supplier_min,
            "commercial_no_impact_allowed": no_impact_allowed,
        }

    @api.constrains(
        "gate_line_id", "version_id", "predecessor_ids", "duration_days",
        "commercial_control_required", "commercial_customer_record_min",
        "commercial_supplier_record_min", "commercial_no_impact_allowed",
    )
    def _check_activity_governance(self):
        for activity in self:
            if activity.gate_line_id.version_id != activity.version_id:
                raise ValidationError(_("The activity gate must belong to the same programme version."))
            if activity in activity.predecessor_ids:
                raise ValidationError(_("An activity cannot depend on itself."))
            if activity.predecessor_ids.filtered(lambda predecessor: predecessor.version_id != activity.version_id):
                raise ValidationError(_("Activity dependencies cannot cross programme versions."))
            frontier = list(activity.predecessor_ids)
            visited = set()
            while frontier:
                predecessor = frontier.pop()
                if predecessor.id == activity.id:
                    raise ValidationError(_("Activity dependencies cannot contain a cycle."))
                if predecessor.id in visited:
                    continue
                visited.add(predecessor.id)
                frontier.extend(predecessor.predecessor_ids)
            if activity.duration_days < 0:
                raise ValidationError(_("Activity duration cannot be negative."))
            if activity.commercial_customer_record_min < 0 or activity.commercial_supplier_record_min < 0:
                raise ValidationError(_("Commercial record minimums cannot be negative."))
            if activity.commercial_control_required and not (
                activity.commercial_customer_record_min
                or activity.commercial_supplier_record_min
                or activity.commercial_no_impact_allowed
            ):
                raise ValidationError(_(
                    "A commercial-control activity needs a customer/supplier record minimum or an allowed No Impact route."
                ))
            if not activity.commercial_control_required and (
                activity.commercial_customer_record_min
                or activity.commercial_supplier_record_min
                or activity.commercial_no_impact_allowed
            ):
                raise ValidationError(_("Commercial rules may be configured only on a commercial-control activity."))

    @api.constrains("owner_designation_id", "approver_designation_id")
    def _check_activity_role_separation(self):
        """Enforce role separation when either accountable role is assigned."""
        for activity in self:
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
    artifact_code = fields.Char(related="artifact_master_id.code", readonly=True)
    artifact_type = fields.Selection(related="artifact_master_id.artifact_type", readonly=True)
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


class HjigProgrammeRunScopeDecision(models.Model):
    _name = "hjig.programme.run.scope.decision"
    _description = "Programme Conditional Activity Scope Decision"
    _order = "run_id, template_activity_id"

    run_id = fields.Many2one(
        "hjig.programme.run", required=True, ondelete="cascade", index=True, readonly=True
    )
    template_activity_id = fields.Many2one(
        "hjig.programme.template.activity", required=True, ondelete="restrict", index=True, readonly=True
    )
    activity_code = fields.Char(related="template_activity_id.code", store=True, readonly=True)
    activity_name = fields.Char(related="template_activity_id.name", readonly=True)
    execution_basis = fields.Selection(
        related="template_activity_id.execution_basis", store=True, readonly=True
    )
    decision = fields.Selection(
        [("pending", "Pending"), ("include", "Include"), ("exclude", "Exclude / N/A")],
        required=True,
        default="pending",
    )
    reason = fields.Text()
    decided_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    decided_on = fields.Datetime(readonly=True, copy=False)

    _run_activity_unique = models.Constraint(
        "UNIQUE(run_id, template_activity_id)",
        "A conditional activity may have only one scope decision in a programme run.",
    )

    @api.constrains("run_id", "template_activity_id", "decision", "reason")
    def _check_scope_decision(self):
        for item in self:
            if item.template_activity_id.version_id != item.run_id.template_version_id:
                raise ValidationError(_("The conditional activity must belong to the run template version."))
            if not item.template_activity_id.conditional:
                raise ValidationError(_("Scope decisions are allowed only for conditional activities."))
            if item.decision == "exclude" and not (item.reason or "").strip():
                raise ValidationError(_("An exclusion reason is required for audit traceability."))

    def write(self, vals):
        if self.filtered(lambda item: item.run_id.state != "draft"):
            raise ValidationError(_("Conditional scope decisions are frozen after execution generation."))
        if "decision" in vals:
            for item in self:
                project = item.run_id.project_id
                permitted = (
                    item.run_id.template_version_id.template_id.owner_designation_id._holders_for_project(project)
                    | item.run_id.template_version_id.template_id.approver_designation_id._holders_for_project(project)
                )
                if self.env.user not in permitted:
                    raise UserError(_("Only a current programme owner or approver designation holder may decide activity scope."))
            vals = dict(vals)
            vals.update({"decided_by_id": self.env.user.id, "decided_on": fields.Datetime.now()})
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.run_id.state != "draft"):
            raise UserError(_("Generated programme scope decisions cannot be deleted."))
        return super().unlink()


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
    checklist_instance_ids = fields.One2many(
        "hjig.programme.checklist.instance", "run_id", readonly=True
    )
    scope_decision_ids = fields.One2many(
        "hjig.programme.run.scope.decision", "run_id", string="Conditional Scope Decisions"
    )
    sourcebridge_engagement_ids = fields.One2many(
        "hjig.sourcebridge.engagement", "programme_run_id", string="SourceBridge Engagements"
    )
    portfolio_guard_id = fields.Many2one(
        "hjig.portfolio.guard", ondelete="restrict", index=True, tracking=True
    )
    current_gate_ids = fields.Many2many(
        "hjig.programme.run.gate", compute="_compute_employee_workbench",
        string="Current Gate / Control",
    )
    upcoming_gate_ids = fields.Many2many(
        "hjig.programme.run.gate", compute="_compute_employee_workbench",
        string="Upcoming Gates",
    )
    completed_gate_ids = fields.Many2many(
        "hjig.programme.run.gate", compute="_compute_employee_workbench",
        string="Completed Gates",
    )
    current_activity_ids = fields.Many2many(
        "project.task", compute="_compute_employee_workbench", string="Current Gate Activities"
    )
    blocked_activity_ids = fields.Many2many(
        "project.task", compute="_compute_employee_workbench", string="Blocked Activities"
    )
    current_form_requirement_ids = fields.Many2many(
        "hjig.programme.run.artifact", compute="_compute_employee_workbench",
        string="Current Forms and Evidence",
    )
    current_instruction_requirement_ids = fields.Many2many(
        "hjig.programme.run.artifact", compute="_compute_employee_workbench",
        string="Current Operating Instructions",
    )
    current_gate_count = fields.Integer(compute="_compute_employee_workbench")
    current_activity_count = fields.Integer(compute="_compute_employee_workbench")
    blocked_activity_count = fields.Integer(compute="_compute_employee_workbench")
    missing_evidence_count = fields.Integer(compute="_compute_employee_workbench")

    _project_unique = models.Constraint(
        "UNIQUE(project_id)",
        "A project can have only one programme run.",
    )

    @api.constrains("sale_order_id", "portfolio_guard_id")
    def _check_sale_order_run_scope(self):
        """One order normally has one run; PortfolioGuard is the governed exception."""
        for run in self:
            siblings = self.search([
                ("sale_order_id", "=", run.sale_order_id.id),
                ("id", "!=", run.id),
            ])
            if not siblings:
                continue
            portfolio = run.portfolio_guard_id
            if (
                not portfolio
                or portfolio.sale_order_id != run.sale_order_id
                or siblings.filtered(lambda item: item.portfolio_guard_id != portfolio)
            ):
                raise ValidationError(_(
                    "An Order Punch can activate multiple programme runs only inside one PortfolioGuard umbrella."
                ))

    _EXECUTION_STAGE_DEFINITIONS = (
        ("01 — To Do", 10, False),
        ("02 — In Progress", 20, False),
        ("03 — Waiting for Evidence Approval", 30, False),
        ("04 — Done", 40, True),
    )

    @api.depends(
        "gate_ids.state", "gate_ids.sequence", "task_ids.stage_id.fold",
        "task_ids.hjig_execution_blocked", "task_ids.hjig_governance_stage_id",
        "artifact_requirement_ids.status", "artifact_requirement_ids.run_gate_id",
        "artifact_requirement_ids.artifact_master_id.artifact_type",
    )
    def _compute_employee_workbench(self):
        for run in self:
            open_gates = run.gate_ids.filtered(lambda gate: gate.required and gate.state != "approved")
            current_sequence = min(open_gates.mapped("sequence"), default=False)
            current_gates = open_gates.filtered(
                lambda gate: current_sequence is not False and gate.sequence == current_sequence
            )
            current_stages = current_gates.mapped("stage_id")
            current_tasks = run.task_ids.filtered(
                lambda task: task.hjig_governance_stage_id in current_stages and not task.stage_id.fold
            )
            current_requirements = run.artifact_requirement_ids.filtered(
                lambda item: item.run_gate_id in current_gates
            )
            forms = current_requirements.filtered(
                lambda item: item.artifact_master_id.artifact_type == "form"
            )
            instructions = current_requirements.filtered(
                lambda item: item.artifact_master_id.artifact_type == "sop"
            )
            run.current_gate_ids = current_gates
            run.upcoming_gate_ids = open_gates - current_gates
            run.completed_gate_ids = run.gate_ids.filtered(lambda gate: gate.state == "approved")
            run.current_activity_ids = current_tasks
            run.blocked_activity_ids = current_tasks.filtered("hjig_execution_blocked")
            run.current_form_requirement_ids = forms
            run.current_instruction_requirement_ids = instructions
            run.current_gate_count = len(current_gates)
            run.current_activity_count = len(current_tasks)
            run.blocked_activity_count = len(run.blocked_activity_ids)
            run.missing_evidence_count = len(forms.filtered(lambda item: item.status != "approved"))

    def action_open_current_activities(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Current Gate Activities — %s") % self.project_id.display_name,
            "res_model": "project.task",
            "view_mode": "list,form",
            "domain": [("id", "in", self.current_activity_ids.ids)],
            "context": {"create": False, "delete": False},
        }

    def action_open_current_forms(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Current Forms and Evidence — %s") % self.project_id.display_name,
            "res_model": "hjig.programme.run.artifact",
            "view_mode": "list,form",
            "domain": [("id", "in", self.current_form_requirement_ids.ids)],
            "context": {"create": False, "delete": False},
        }

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

    def _ensure_scope_decisions(self):
        Decision = self.env["hjig.programme.run.scope.decision"]
        for run in self:
            existing = run.scope_decision_ids.mapped("template_activity_id")
            for activity in run.template_version_id.activity_line_ids.filtered("conditional") - existing:
                Decision.create({"run_id": run.id, "template_activity_id": activity.id})
        return True

    def _included_activities(self):
        self.ensure_one()
        excluded = self.scope_decision_ids.filtered(
            lambda decision: decision.decision == "exclude"
        ).mapped("template_activity_id")
        return self.template_version_id.activity_line_ids - excluded

    def _assert_project_designation_assignments(self):
        for run in self:
            version = run.template_version_id
            designations = (
                version.template_id.owner_designation_id
                | version.template_id.approver_designation_id
                | version.activity_line_ids.mapped("owner_designation_id")
                | version.activity_line_ids.mapped("approver_designation_id")
                | version.activity_line_ids.mapped("coordinator_designation_id")
                | version.activity_line_ids.mapped("support_designation_ids")
                | version.checklist_item_ids.mapped("owner_designation_id")
                | version.checklist_item_ids.mapped("approver_designation_id")
                | version.artifact_rule_ids.mapped("artifact_master_id.owner_designation_id")
                | version.artifact_rule_ids.mapped("artifact_master_id.approver_designation_id")
            )
            if "session_line_ids" in version._fields:
                designations |= version.session_line_ids.mapped("owner_designation_id")
                designations |= version.session_line_ids.mapped("approver_designation_id")
            missing = designations.filtered(
                lambda designation: not designation._holders_for_project(run.project_id)
            )
            if missing:
                raise ValidationError(
                    _("Assign project-specific holders before execution: %s")
                    % ", ".join(missing.mapped("code"))
                )
            required_users = self.env["res.users"]
            for designation in designations:
                required_users |= designation._holders_for_project(run.project_id)
            missing_team_users = required_users - run.project_id.hjig_authorized_user_ids
            if missing_team_users:
                run.project_id.hjig_authorized_user_ids = [
                    (4, user.id) for user in missing_team_users
                ]
        return True

    def _ensure_project_execution_stages(self):
        """Create one predictable employee board for each governed project."""
        self.ensure_one()
        Stage = self.env["project.task.type"]
        project_stages = Stage.search([("project_ids", "in", self.project_id.id)])
        stage_by_name = {stage.name: stage for stage in project_stages}
        first_stage = Stage
        for name, sequence, folded in self._EXECUTION_STAGE_DEFINITIONS:
            stage = stage_by_name.get(name)
            if not stage:
                stage = Stage.create({
                    "name": name,
                    "sequence": sequence,
                    "fold": folded,
                    "project_ids": [(4, self.project_id.id)],
                })
                stage_by_name[name] = stage
            elif stage.fold != folded:
                stage.fold = folded
            if name == self._EXECUTION_STAGE_DEFINITIONS[0][0]:
                first_stage = stage
        return first_stage

    def _activity_scope_values(self, activity):
        self.ensure_one()
        if activity.execution_basis == "project":
            return [(False, False)]
        moulds = self._approved_moulds()
        if activity.execution_basis == "mould":
            return [(mould, False) for mould in moulds]
        parts = self.env["x_mould_part"].search([
            ("x_mould_id", "in", moulds.ids), ("x_active", "=", True),
        ])
        return [(part.x_mould_id, part) for part in parts]

    @staticmethod
    def _add_working_days(start, days):
        """Apply the approved template's working-day offset without counting weekends."""
        result = start
        remaining = max(days, 0)
        while remaining:
            result += timedelta(days=1)
            if result.weekday() < 5:
                remaining -= 1
        return result

    def _activity_plan_values(self, activity):
        self.ensure_one()
        if not self.project_id.date_start:
            return {}
        project_start = fields.Datetime.to_datetime(self.project_id.date_start).replace(hour=9)
        planned_start = self._add_working_days(project_start, activity.offset_days)
        deadline = self._add_working_days(planned_start, max(activity.duration_days - 1, 0)).replace(hour=17)
        return {"planned_date_begin": planned_start, "date_deadline": deadline}

    def _sync_activity_tasks(self):
        Task = self.env["project.task"]
        for run in self:
            start_stage = run._ensure_project_execution_stages()
            included = run._included_activities()
            for activity in included.sorted(lambda line: (line.sequence, line.id)):
                for mould, part in run._activity_scope_values(activity):
                    scope_key = (
                        "C:%s" % part.id if part else "M:%s" % mould.id if mould else "P"
                    )
                    existing = run.task_ids.filtered(
                        lambda task: task.hjig_template_activity_id == activity
                        and task.hjig_execution_scope_key == scope_key
                    )
                    if existing:
                        continue
                    scope_label = part.x_part_number if part else mould.x_mould_number if mould else False
                    task_values = {
                        "name": "%s%s" % (activity.name, " — %s" % scope_label if scope_label else ""),
                        "project_id": run.project_id.id,
                        "stage_id": start_stage.id,
                        "sequence": activity.sequence,
                        "user_ids": [(6, 0, activity.owner_designation_id._holders_for_project(run.project_id).ids)],
                        "hjig_programme_run_id": run.id,
                        "hjig_template_activity_id": activity.id,
                        "hjig_governance_stage_id": activity.gate_line_id.stage_id.id,
                        "hjig_owner_designation_id": activity.owner_designation_id.id,
                        "hjig_approver_designation_id": activity.approver_designation_id.id,
                        "hjig_coordinator_designation_id": activity.coordinator_designation_id.id,
                        "hjig_support_designation_ids": [(6, 0, activity.support_designation_ids.ids)],
                        "hjig_execution_basis": activity.execution_basis,
                        "hjig_execution_scope_key": scope_key,
                        "hjig_mould_id": mould.id if mould else False,
                        "hjig_part_id": part.id if part else False,
                        "hjig_commercial_control_required": activity.commercial_control_required,
                        "hjig_commercial_customer_record_min": activity.commercial_customer_record_min,
                        "hjig_commercial_supplier_record_min": activity.commercial_supplier_record_min,
                        "hjig_commercial_no_impact_allowed": activity.commercial_no_impact_allowed,
                        "hjig_commercial_control_state": (
                            "draft" if activity.commercial_control_required else "not_required"
                        ),
                    }
                    task_values.update(run._activity_plan_values(activity))
                    Task.with_context(**workflow_context()).create(task_values)
            stale = run.task_ids.filtered(
                lambda task: task.hjig_template_activity_id not in included
            )
            if stale:
                raise ValidationError(_("Excluded conditional activities already have generated tasks."))
        return True

    def _scoped_predecessor_tasks(self, task, predecessor_activity):
        self.ensure_one()
        candidates = self.task_ids.filtered(
            lambda item: item.hjig_template_activity_id == predecessor_activity
        )
        if predecessor_activity.execution_basis == "project":
            return candidates.filtered(lambda item: item.hjig_execution_scope_key == "P")
        if task.hjig_execution_basis == "project":
            return candidates
        if predecessor_activity.execution_basis == "mould":
            return candidates.filtered(lambda item: item.hjig_mould_id == task.hjig_mould_id)
        if task.hjig_execution_basis == "component":
            return candidates.filtered(lambda item: item.hjig_part_id == task.hjig_part_id)
        return candidates.filtered(lambda item: item.hjig_mould_id == task.hjig_mould_id)

    def _sync_task_dependencies(self):
        for run in self:
            included = run._included_activities()
            for task in run.task_ids:
                predecessors = self.env["project.task"]
                for predecessor in task.hjig_template_activity_id.predecessor_ids & included:
                    predecessors |= run._scoped_predecessor_tasks(task, predecessor)
                task.with_context(**workflow_context()).depend_on_ids = [(6, 0, predecessors.ids)]
        return True

    def _sync_dependency_planning(self):
        """Calculate an executable plan from the approved dependency graph."""
        for run in self.filtered(lambda item: item.project_id.date_start):
            pending = run.task_ids
            while pending:
                ready = pending.filtered(lambda task: not (task.depend_on_ids & pending))
                if not ready:
                    raise ValidationError(_("Generated programme dependencies contain a cycle."))
                for task in ready.sorted(lambda item: (item.sequence, item.id)):
                    activity = task.hjig_template_activity_id
                    baseline = run._activity_plan_values(activity)
                    planned_start = baseline["planned_date_begin"]
                    predecessor_deadlines = [
                        deadline for deadline in task.depend_on_ids.mapped("date_deadline") if deadline
                    ]
                    if predecessor_deadlines:
                        latest = fields.Datetime.to_datetime(max(predecessor_deadlines))
                        dependency_start = fields.Datetime.to_datetime(
                            run._add_working_days(latest.date(), 1)
                        ).replace(hour=9)
                        planned_start = max(planned_start, dependency_start)
                    deadline = run._add_working_days(
                        planned_start, max(activity.duration_days - 1, 0)
                    ).replace(hour=17)
                    task.with_context(**workflow_context()).write({
                        "planned_date_begin": planned_start,
                        "date_deadline": deadline,
                    })
                pending -= ready
            final_deadlines = [deadline for deadline in run.task_ids.mapped("date_deadline") if deadline]
            if final_deadlines:
                final_date = fields.Datetime.to_datetime(max(final_deadlines)).date()
                run.project_id.with_context(**workflow_context()).write({
                    "date_start": fields.Date.to_string(run.project_id.date_start),
                    "date": fields.Date.to_string(final_date),
                })
        return True

    def action_generate_execution(self):
        for run in self:
            if run.state == "generated":
                continue
            if run.template_version_id.state != "approved":
                raise ValidationError(_("Only an approved programme version can generate execution records."))
            run._assert_project_designation_assignments()
            run._ensure_scope_decisions()
            if run.scope_decision_ids.filtered(lambda decision: decision.decision == "pending"):
                raise ValidationError(
                    _("Decide every conditional activity scope before generating programme execution.")
                )
            version = run.template_version_id
            run._sync_activity_tasks()
            run._sync_task_dependencies()
            run._sync_dependency_planning()
            run._sync_execution_scopes()
            payload = version._definition_payload()
            run.with_context(hjig_run_workflow=True).write({
                "state": "generated",
                "activated_on": fields.Datetime.now(),
                "activated_by_id": self.env.user.id,
                "definition_hash": version.definition_hash,
                "snapshot_json": payload,
            })
        return True

    def _approved_moulds(self):
        self.ensure_one()
        return self.env["x_mould"].search([
            ("x_project_id", "=", self.project_id.id),
            ("x_workflow_state", "=", "approved"),
        ])

    def _create_gate_scope(self, template_gate, mould=False):
        self.ensure_one()
        gate = self.env["hjig.programme.run.gate"].create({
            "run_id": self.id,
            "template_gate_id": template_gate.id,
            "stage_id": template_gate.stage_id.id,
            "sequence": template_gate.sequence,
            "required": template_gate.required,
            "mould_id": mould.id if mould else False,
        })
        for rule in self.template_version_id.artifact_rule_ids.filtered(
            lambda item: item.stage_id == template_gate.stage_id
        ):
            self.env["hjig.programme.run.artifact"].create({
                "run_id": self.id,
                "run_gate_id": gate.id,
                "artifact_master_id": rule.artifact_master_id.id,
                "stage_id": rule.stage_id.id,
                "mould_id": mould.id if mould else False,
                "mandatory": rule.mandatory,
            })
        for template_item in self.template_version_id.checklist_item_ids.filtered(
            lambda item: item.gate_line_id == template_gate
            and item.execution_basis == ("mould" if mould else "project")
        ):
            instance = self.env["hjig.programme.checklist.instance"].create({
                "run_id": self.id,
                "run_gate_id": gate.id,
                "template_item_id": template_item.id,
                "mould_id": mould.id if mould else False,
            })
            threshold = template_item.auto_na_risk_below
            if threshold:
                applicable_risk = self.env["hjig.project.risk"].search_count([
                    ("project_id", "=", self.project_id.id),
                    ("status", "!=", "resolved"),
                    ("risk_score", ">=", threshold),
                ])
                if not applicable_risk:
                    instance.with_context(hjig_checklist_workflow=True).write({
                        "status": "na",
                        "remarks": _("Automatically N/A: no unresolved project risk has score %s or higher.") % threshold,
                        "ticked_by_id": self.env.user.id,
                        "ticked_on": fields.Datetime.now(),
                        "automatic_disposition": True,
                    })
        return gate

    def _ensure_shared_checklist_items(self, template_gate):
        self.ensure_one()
        for template_item in self.template_version_id.checklist_item_ids.filtered(
            lambda item: item.gate_line_id == template_gate and item.execution_basis == "project"
        ):
            existing = self.checklist_instance_ids.filtered(
                lambda item: item.template_item_id == template_item and not item.mould_id
            )
            if not existing:
                self.env["hjig.programme.checklist.instance"].create({
                    "run_id": self.id,
                    "template_item_id": template_item.id,
                })

    def _sync_execution_scopes(self):
        for run in self:
            moulds = run._approved_moulds()
            for template_gate in run.template_version_id.gate_line_ids.sorted(
                lambda line: (line.sequence, line.id)
            ):
                scopes = moulds if template_gate.execution_basis == "mould" else [False]
                if template_gate.execution_basis == "mould":
                    run._ensure_shared_checklist_items(template_gate)
                for mould in scopes:
                    existing = run.gate_ids.filtered(
                        lambda gate: gate.template_gate_id == template_gate
                        and gate.mould_id.id == (mould.id if mould else False)
                    )
                    if not existing:
                        run._create_gate_scope(template_gate, mould=mould)
        return True

    def action_sync_mould_execution(self):
        for run in self:
            if run.state != "generated":
                raise UserError(_("Mould execution can be synchronised only after programme generation."))
            run._sync_activity_tasks()
            run._sync_task_dependencies()
            run._sync_execution_scopes()
        return True

    def action_close_run(self):
        for run in self:
            if run.state != "generated":
                raise UserError(_("Only a generated programme run can be closed."))
            if run.gate_ids.filtered(lambda gate: gate.required and gate.state != "approved"):
                raise ValidationError(_("All required programme gates must be approved before closure."))
            mould_gates = run.template_version_id.gate_line_ids.filtered(
                lambda gate: gate.required and gate.execution_basis == "mould"
            )
            approved_moulds = run._approved_moulds()
            if mould_gates and not approved_moulds:
                raise ValidationError(_("At least one approved mould plan is required for this programme."))
            for mould in approved_moulds:
                missing = mould_gates.filtered(
                    lambda template_gate: not run.gate_ids.filtered(
                        lambda gate: gate.template_gate_id == template_gate and gate.mould_id == mould
                    )
                )
                if missing:
                    raise ValidationError(_("Synchronise and approve every required gate for each approved mould."))
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
    name = fields.Char(compute="_compute_name", store=True)
    template_gate_id = fields.Many2one(
        "hjig.programme.template.gate", required=True, readonly=True, ondelete="restrict"
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, readonly=True, ondelete="restrict", index=True
    )
    stage_type = fields.Selection(related="stage_id.stage_type", store=True, readonly=True)
    sequence = fields.Integer(required=True, readonly=True)
    required = fields.Boolean(default=True, readonly=True)
    mould_id = fields.Many2one("x_mould", ondelete="restrict", index=True, readonly=True)
    checklist_instance_ids = fields.One2many(
        "hjig.programme.checklist.instance", "run_gate_id", readonly=True
    )
    state = fields.Selection(
        [("blocked", "Blocked"), ("ready", "Ready"), ("approved", "Approved")],
        default="blocked",
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    approval_note = fields.Text(tracking=True)
    block_reason = fields.Text(compute="_compute_block_reason", string="What Is Blocking This Gate")

    _run_gate_unique = models.Constraint(
        "UNIQUE(run_id, template_gate_id, mould_id)",
        "A programme gate can appear only once per project or mould scope.",
    )

    @api.depends("stage_id.name", "mould_id.x_mould_number")
    def _compute_name(self):
        for gate in self:
            gate.name = "%s%s" % (
                gate.stage_id.name or _("Gate"),
                " — %s" % gate.mould_id.x_mould_number if gate.mould_id else "",
            )

    @api.depends(
        "state", "run_id.task_ids.stage_id.fold", "run_id.task_ids.hjig_commercial_control_current",
        "run_id.artifact_requirement_ids.status", "run_id.checklist_instance_ids.status",
    )
    def _compute_block_reason(self):
        for gate in self:
            gate.block_reason = False if gate.state == "approved" else "\n".join(gate._blocking_reasons())

    @api.constrains("run_id", "template_gate_id", "mould_id")
    def _check_gate_scope(self):
        for gate in self:
            if gate.template_gate_id.execution_basis == "mould" and not gate.mould_id:
                raise ValidationError(_("A mould-basis gate requires a mould."))
            if gate.template_gate_id.execution_basis == "project" and gate.mould_id:
                raise ValidationError(_("A project-basis gate cannot carry a mould."))
            if gate.mould_id and gate.mould_id.x_project_id != gate.run_id.project_id:
                raise ValidationError(_("The programme gate mould must belong to the run project."))
            duplicate = self.search_count([
                ("run_id", "=", gate.run_id.id),
                ("template_gate_id", "=", gate.template_gate_id.id),
                ("mould_id", "=", gate.mould_id.id if gate.mould_id else False),
                ("id", "!=", gate.id),
            ])
            if duplicate:
                raise ValidationError(_("A programme gate can appear only once in the same scope."))

    def _blocking_reasons(self):
        self.ensure_one()
        reasons = []
        earlier = self.run_id.gate_ids.filtered(
            lambda gate: gate.required
            and gate.sequence < self.sequence
            and gate.state != "approved"
            and (not self.mould_id or not gate.mould_id or gate.mould_id == self.mould_id)
        )
        if earlier:
            reasons.append(_("earlier required gates are not approved"))
        tasks = self.run_id.task_ids.filtered(
            lambda task: task.hjig_governance_stage_id == self.stage_id
            and (
                not self.mould_id
                or task.hjig_execution_basis == "project"
                or task.hjig_mould_id == self.mould_id
            )
        )
        if tasks.filtered(lambda task: not task.stage_id.fold):
            reasons.append(_("gate activities are not complete"))
        commercial_tasks = tasks.filtered("hjig_commercial_control_required")
        if commercial_tasks.filtered(lambda task: not task._hjig_commercial_control_is_current()):
            reasons.append(_("commercial milestone controls are not approved or their source records changed"))
        artifacts = self.run_id.artifact_requirement_ids.filtered(
            lambda item: item.run_gate_id == self and item.mandatory
        )
        if artifacts.filtered(lambda item: item.status != "approved"):
            reasons.append(_("mandatory SOP/Form evidence is not approved"))
        checklist = self.run_id.checklist_instance_ids.filtered(
            lambda item: item.template_item_id.gate_line_id == self.template_gate_id
            and (not item.mould_id or item.mould_id == self.mould_id)
        )
        if not checklist:
            reasons.append(_("authoritative gate checklist content is missing"))
        elif checklist.filtered(
            lambda item: item.mandatory and item.status not in ("pass", "na")
        ):
            reasons.append(_("mandatory checklist items are not Pass or controlled N/A"))
        return reasons

    def action_refresh_readiness(self):
        for gate in self.filtered(lambda item: item.state != "approved"):
            gate.with_context(hjig_gate_workflow=True).write({
                "state": "blocked" if gate._blocking_reasons() else "ready"
            })
        return True

    def action_approve_gate(self):
        if self.filtered(lambda control: control.stage_type == "milestone"):
            raise UserError(_("Use Confirm Milestone for a direct-entry or terminal milestone."))
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_document_controller"):
            raise UserError(_("Only an authorised Document Controller may approve a programme gate."))
        for gate in self:
            gate.action_refresh_readiness()
            if gate.state != "ready":
                raise ValidationError(_("Gate cannot close: %s.") % ", ".join(gate._blocking_reasons()))
            approvers = gate.run_id.template_version_id.template_id.approver_designation_id._holders_for_project(
                gate.run_id.project_id
            )
            if self.env.user not in approvers:
                raise UserError(_("You do not hold the required programme approver designation."))
            gate.with_context(hjig_gate_workflow=True).write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
            })
        return True

    def action_confirm_milestone(self):
        for control in self:
            if control.stage_type != "milestone":
                raise UserError(_("Only a route milestone may use milestone confirmation."))
            control.action_refresh_readiness()
            if control.state != "ready":
                raise ValidationError(
                    _("Milestone cannot be confirmed: %s.")
                    % ", ".join(control._blocking_reasons())
                )
            approvers = (
                control.run_id.template_version_id.template_id.approver_designation_id
                ._holders_for_project(control.run_id.project_id)
            )
            if self.env.user not in approvers:
                raise UserError(_("You do not hold the required programme approver designation."))
            control.with_context(hjig_gate_workflow=True).write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
                "approval_note": _("Controlled route milestone confirmed; this is not a formal GO / NO-GO gate."),
            })
        return True

    def write(self, vals):
        frozen = {"run_id", "template_gate_id", "stage_id", "sequence", "required", "mould_id"}
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
    project_id = fields.Many2one(related="run_id.project_id", store=True, readonly=True, index=True)
    run_gate_id = fields.Many2one(
        "hjig.programme.run.gate", required=True, ondelete="cascade", index=True, readonly=True
    )
    artifact_master_id = fields.Many2one(
        "hjig.governance.artifact.master", required=True, ondelete="restrict", index=True
    )
    artifact_code = fields.Char(related="artifact_master_id.code", store=True, readonly=True)
    artifact_type = fields.Selection(related="artifact_master_id.artifact_type", readonly=True)
    employee_quick_guide = fields.Text(related="artifact_master_id.employee_quick_guide", readonly=True)
    entry_control_summary = fields.Text(related="artifact_master_id.entry_control_summary", readonly=True)
    hard_stop_summary = fields.Text(related="artifact_master_id.hard_stop_summary", readonly=True)
    exit_control_summary = fields.Text(related="artifact_master_id.exit_control_summary", readonly=True)
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    mandatory = fields.Boolean(default=True, readonly=True)
    mould_id = fields.Many2one("x_mould", ondelete="restrict", index=True, readonly=True)
    status = fields.Selection(
        [("required", "Required"), ("available", "Available"), ("approved", "Approved")],
        compute="_compute_status",
        store=True,
    )
    project_document_id = fields.Many2one("hjig.project.document", ondelete="restrict")
    sor_id = fields.Many2one("hjig.sor", string="Native SOR Record", ondelete="restrict")
    bop_id = fields.Many2one("hjig.bop", string="Native BOP Register", ondelete="restrict")
    mould_plan_id = fields.Many2one("x_mould", string="Native Mould Planning Record", ondelete="restrict")
    risk_count = fields.Integer(compute="_compute_risk_checkpoint")
    unresolved_escalated_risk_count = fields.Integer(compute="_compute_risk_checkpoint")
    risk_reviewed = fields.Boolean(default=False, readonly=True)
    risk_review_note = fields.Text()
    risk_reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    risk_reviewed_on = fields.Datetime(readonly=True, copy=False)

    _run_artifact_stage_unique = models.Constraint(
        "UNIQUE(run_id, artifact_master_id, stage_id, mould_id)",
        "A programme-run SOP/Form requirement may appear only once per gate scope.",
    )

    @api.depends(
        "project_document_id", "project_document_id.status",
        "sor_id", "sor_id.state", "bop_id", "bop_id.state",
        "mould_plan_id", "mould_plan_id.x_workflow_state", "risk_reviewed", "risk_count",
    )
    def _compute_status(self):
        for requirement in self:
            document = requirement.project_document_id
            if requirement.sor_id:
                requirement.status = "approved" if requirement.sor_id.state == "frozen" else "available"
            elif requirement.bop_id:
                requirement.status = "approved" if requirement.bop_id.state == "frozen" else "available"
            elif requirement.mould_plan_id:
                requirement.status = (
                    "approved" if requirement.mould_plan_id.x_workflow_state == "approved" else "available"
                )
            elif requirement.artifact_code == "FRM-006":
                requirement.status = (
                    "approved" if requirement.risk_reviewed and requirement.risk_count
                    else "available" if requirement.risk_count else "required"
                )
            else:
                requirement.status = (
                    "approved" if document and document.status == "approved"
                    else "available" if document else "required"
                )

    @api.constrains("run_id", "run_gate_id", "stage_id", "mould_id")
    def _check_gate_scope(self):
        for requirement in self:
            gate = requirement.run_gate_id
            if gate.run_id != requirement.run_id:
                raise ValidationError(_("The SOP/Form requirement gate must belong to the same programme run."))
            if gate.stage_id != requirement.stage_id or gate.mould_id != requirement.mould_id:
                raise ValidationError(_("The SOP/Form requirement must match its gate and mould scope."))
            duplicate = self.search_count([
                ("run_id", "=", requirement.run_id.id),
                ("artifact_master_id", "=", requirement.artifact_master_id.id),
                ("stage_id", "=", requirement.stage_id.id),
                ("mould_id", "=", requirement.mould_id.id if requirement.mould_id else False),
                ("id", "!=", requirement.id),
            ])
            if duplicate:
                raise ValidationError(_("A programme SOP/Form requirement can appear only once in the same scope."))

    @api.depends("project_id")
    def _compute_risk_checkpoint(self):
        Risk = self.env["hjig.project.risk"]
        for requirement in self:
            domain = [("project_id", "=", requirement.project_id.id)]
            requirement.risk_count = Risk.search_count(domain) if requirement.project_id else 0
            requirement.unresolved_escalated_risk_count = Risk.search_count(
                domain + [("status", "!=", "resolved"), ("risk_score", ">=", 16)]
            ) if requirement.project_id else 0

    @api.constrains("project_document_id", "sor_id", "bop_id", "mould_plan_id")
    def _check_controlled_record(self):
        for requirement in self:
            linked = [
                bool(requirement.project_document_id), bool(requirement.sor_id),
                bool(requirement.bop_id), bool(requirement.mould_plan_id)
            ]
            if sum(linked) > 1:
                raise ValidationError(_("Link only one authoritative controlled record; duplicate evidence is not allowed."))
            if requirement.project_document_id and requirement.artifact_code in {
                "FRM-003", "FRM-004", "FRM-005", "FRM-006",
            }:
                raise ValidationError(
                    _("This requirement is completed directly in its native Odoo form; do not link a Drive document.")
                )
            if requirement.sor_id:
                if requirement.artifact_code != "FRM-003":
                    raise ValidationError(_("A native SOR record may satisfy only FRM-003."))
                if requirement.sor_id.project_id != requirement.run_id.project_id:
                    raise ValidationError(_("The native SOR record must belong to the programme-run project."))
            if requirement.bop_id:
                if requirement.artifact_code != "FRM-004":
                    raise ValidationError(_("A native BOP register may satisfy only FRM-004."))
                if requirement.bop_id.project_id != requirement.run_id.project_id:
                    raise ValidationError(_("The native BOP register must belong to the programme-run project."))
            if requirement.mould_plan_id:
                if requirement.artifact_code != "FRM-005":
                    raise ValidationError(_("A native Mould Planning record may satisfy only FRM-005."))
                if requirement.mould_plan_id.x_project_id != requirement.run_id.project_id:
                    raise ValidationError(_("The native Mould Planning record must belong to the programme-run project."))
                if requirement.mould_id and requirement.mould_plan_id != requirement.mould_id:
                    raise ValidationError(_("The native Mould Planning record must match the requirement's mould scope."))
        for requirement in self.filtered("project_document_id"):
            document = requirement.project_document_id
            if document.project_id != requirement.run_id.project_id:
                raise ValidationError(_("The controlled document must belong to the programme-run project."))
            if document.artifact_master_id != requirement.artifact_master_id:
                raise ValidationError(_("The controlled document does not satisfy this SOP/Form requirement."))
            if document.stage_id != requirement.stage_id:
                raise ValidationError(_("The controlled document is registered against a different gate."))
            if document.mould_id != requirement.mould_id:
                raise ValidationError(_("The controlled document uses a different mould scope."))

    def action_open_authoritative_record(self):
        self.ensure_one()
        code = self.artifact_code
        linked = self.sor_id or self.bop_id or self.mould_plan_id or self.project_document_id
        if linked:
            return {
                "type": "ir.actions.act_window",
                "name": linked.display_name,
                "res_model": linked._name,
                "view_mode": "form",
                "res_id": linked.id,
            }
        action_xmlid = {
            "FRM-003": "new_hongyijig_custom.action_hjig_sor",
            "FRM-004": "new_hongyijig_custom.action_hjig_bop",
            "FRM-005": "new_hongyijig_custom.action_hjig_mould_plan",
            "FRM-006": "new_hongyijig_custom.action_hjig_project_risk",
        }.get(code)
        if action_xmlid:
            action = self.env["ir.actions.actions"]._for_xml_id(action_xmlid)
            project_field = "x_project_id" if code == "FRM-005" else "project_id"
            action["domain"] = [(project_field, "=", self.project_id.id)]
            action["context"] = {
                "default_%s" % project_field: self.project_id.id,
                "hjig_programme_artifact_requirement_id": self.id,
            }
            return action
        return {
            "type": "ir.actions.act_window",
            "name": _("Controlled Project Documents"),
            "res_model": "hjig.project.document",
            "view_mode": "list,form",
            "domain": [
                ("project_id", "=", self.project_id.id),
                ("artifact_master_id", "=", self.artifact_master_id.id),
                ("stage_id", "=", self.stage_id.id),
            ],
            "context": {
                "default_project_id": self.project_id.id,
                "default_artifact_master_id": self.artifact_master_id.id,
                "default_stage_id": self.stage_id.id,
            },
        }

    def action_confirm_risk_review(self):
        for requirement in self:
            if requirement.artifact_code != "FRM-006":
                raise UserError(_("Risk review confirmation is available only for FRM-006."))
            if not requirement.risk_count:
                raise ValidationError(_("Create at least one project risk before confirming the review."))
            if requirement.unresolved_escalated_risk_count:
                raise ValidationError(_("Resolve or formally control every risk scoring 16 or higher first."))
            if not (requirement.risk_review_note or "").strip():
                raise ValidationError(_("Record a short gate-specific risk review note."))
            requirement.with_context(hjig_risk_review_workflow=True).write({
                "risk_reviewed": True,
                "risk_reviewed_by_id": self.env.user.id,
                "risk_reviewed_on": fields.Datetime.now(),
            })
        return True

    def write(self, vals):
        frozen = {
            "run_id", "run_gate_id", "artifact_master_id", "stage_id", "mould_id", "mandatory"
        }
        if frozen.intersection(vals):
            raise ValidationError(_("Generated SOP/Form requirement identity is immutable."))
        evidence_fields = {
            "project_document_id", "sor_id", "bop_id", "mould_plan_id",
            "risk_reviewed", "risk_review_note", "risk_reviewed_by_id", "risk_reviewed_on",
        }
        if evidence_fields.intersection(vals) and self.filtered(
            lambda item: item.run_gate_id.state == "approved"
        ):
            raise ValidationError(_("Approved gate evidence cannot be replaced."))
        risk_control_fields = {"risk_reviewed", "risk_reviewed_by_id", "risk_reviewed_on"}
        if risk_control_fields.intersection(vals) and not self.env.context.get(
            "hjig_risk_review_workflow"
        ):
            raise ValidationError(_("Use the governed risk-review action to confirm the checkpoint."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Generated SOP/Form requirements cannot be deleted."))


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
        "hjig.programme.run", ondelete="restrict", index=True, tracking=True
    )
    sseries_case_id = fields.Many2one(
        "hjig.sseries.case", string="S-Series Handover Case", ondelete="restrict",
        index=True, tracking=True,
    )
    standalone = fields.Boolean(compute="_compute_standalone", store=True, readonly=True)
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
    _sseries_case_unique = models.Constraint(
        "UNIQUE(sseries_case_id)", "An S-Series case can create only one SourceBridge engagement."
    )

    @api.depends("programme_run_id")
    def _compute_standalone(self):
        for engagement in self:
            engagement.standalone = not bool(engagement.programme_run_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    @api.constrains(
        "project_id", "programme_run_id", "sseries_case_id",
        "owner_designation_id", "approver_designation_id",
    )
    def _check_engagement_governance(self):
        for engagement in self:
            if not engagement.programme_run_id and not engagement.sseries_case_id:
                raise ValidationError(_(
                    "SourceBridge requires either a governed programme run or an S-Series handover case."
                ))
            if engagement.programme_run_id and engagement.programme_run_id.project_id != engagement.project_id:
                raise ValidationError(_("SourceBridge must link to the programme run of the same project."))
            if engagement.sseries_case_id.project_id and engagement.sseries_case_id.project_id != engagement.project_id:
                raise ValidationError(_("SourceBridge must link to the project released by its S-Series case."))
            if engagement.owner_designation_id == engagement.approver_designation_id:
                raise ValidationError(_("SourceBridge owner and approver designations must differ."))

    def action_activate(self):
        for engagement in self:
            if engagement.state != "draft":
                raise UserError(_("Only a Draft SourceBridge engagement can be activated."))
            if not engagement.component_ids:
                raise ValidationError(_("SourceBridge requires at least one sourcing component."))
            if not engagement.approver_designation_id._user_holds_for_project(
                self.env.user, engagement.project_id
            ):
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
            "code", "project_id", "programme_run_id", "sseries_case_id", "sale_order_id",
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
            if not engagement.approver_designation_id._user_holds_for_project(
                self.env.user, engagement.project_id
            ):
                raise UserError(_("You do not hold the SourceBridge approver designation."))
            component.with_context(hjig_component_accept=True).write({"status": "accepted"})
        return True

    def unlink(self):
        if self.mapped("engagement_id").filtered(lambda engagement: engagement.state != "draft"):
            raise UserError(_("Active SourceBridge components cannot be deleted."))
        return super().unlink()


class SaleOrder(models.Model):
    _inherit = "sale.order"

    _HJIG_TEMPLATE_PROGRAMME_KEYS = {
        "LGC": "launchguard_complete",
        "LGD": "launchguard_design",
        "LGV": "launchguard_development",
        "TLC": "toollock_control",
        "TLL": "toollock_lite",
    }

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
    hjig_sseries_case_id = fields.Many2one(
        "hjig.sseries.case", string="S-Series Commercial Case", copy=False, readonly=True,
        ondelete="restrict", index=True,
    )
    hjig_order_punch_pdf_url = fields.Char(string="Approved Order Punch PDF", copy=False, tracking=True)
    hjig_commercial_pdf_url = fields.Char(string="Approved Commercial PDF", copy=False, tracking=True)

    def write(self, vals):
        governed = {
            "hjig_programme_version_id", "hjig_project_code", "hjig_project_id", "hjig_programme_run_id",
            "hjig_order_punch_pdf_url", "hjig_commercial_pdf_url",
            "hjig_sseries_case_id",
        }
        if governed.intersection(vals) and self.filtered("hjig_programme_run_id"):
            if not self.env.context.get("hjig_programme_activation"):
                raise ValidationError(_("Order Punch programme selection is frozen after activation."))
        return super().write(vals)

    def _hjig_resolve_activation_project(self):
        """Adopt one governed legacy project; never create a duplicate implicitly."""
        self.ensure_one()
        project = self.hjig_project_id
        Project = self.env["project.project"].with_context(active_test=False)
        if not project and "x_order_reference_id" in Project._fields:
            linked = Project.search([("x_order_reference_id", "=", self.id)])
            if len(linked) > 1:
                raise ValidationError(
                    _("More than one project is linked to this order. Resolve the duplicate linkage before activation.")
                )
            project = linked
        if not project:
            return project
        if project.hjig_project_record_type != "customer":
            raise ValidationError(_("The adopted project must be classified as a Customer Project."))
        if (
            project.partner_id
            and project.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id
        ):
            raise ValidationError(_("The order customer and adopted project customer do not match."))
        if project.company_id and project.company_id != self.company_id:
            raise ValidationError(_("The order company and adopted project company do not match."))
        return project

    def action_activate_hjig_programme(self):
        self.ensure_one()
        existing = self.env["hjig.programme.run"].search([("sale_order_id", "=", self.id)])
        if len(existing) > 1:
            raise ValidationError(_(
                "This is a PortfolioGuard umbrella order. Open its child programme runs from PortfolioGuard."
            ))
        if existing:
            return self._hjig_run_action(existing)
        if self.state not in ("sale", "done"):
            raise UserError(_("The Order Punch must be confirmed before programme activation."))
        version = self.hjig_programme_version_id
        if not version or version.state != "approved" or not version.is_current:
            raise ValidationError(_("Select the current approved programme version before activation."))
        project = self._hjig_resolve_activation_project()
        programme_key = self._HJIG_TEMPLATE_PROGRAMME_KEYS.get(version.template_id.code)
        if programme_key and project and project.hjig_programme != programme_key:
            raise ValidationError(
                _("The adopted project's configured programme route does not match the selected template.")
            )
        project_code = (self.hjig_project_code or project.x_project_code or "").strip().upper()
        if not project_code:
            raise ValidationError(_("Enter the approved governed project code before activation."))
        code_parts = project_code.split("-")
        if len(code_parts) != 4 or code_parts[1] != version.template_id.code:
            raise ValidationError(
                _("The Project Code programme segment must match the selected programme template (%s).")
                % version.template_id.code
            )
        sseries_case = self.hjig_sseries_case_id
        if sseries_case:
            if sseries_case.sale_order_id != self or sseries_case.stage not in ("s6_handover", "b0_released"):
                raise ValidationError(_("The linked S-Series case has not reached governed S6 handover."))
            order_punch = sseries_case.artifact_ids.filtered(
                lambda item: item.code == "S5-ORDER-PUNCH" and item.state == "approved"
            )[:1]
            proposal_codes = {
                "launchguard_complete": "LGC-03", "launchguard_design": "LGD-03",
                "launchguard_development": "LGV-03", "toollock_control": "TLC-03",
                "toollock_lite": "TLL-03", "sourcebridge_only": "SB-03",
            }
            proposal_code = "PG-03" if sseries_case.form_type == "portfolio_guard" else proposal_codes.get(
                sseries_case.programme_route
            )
            proposal = sseries_case.artifact_ids.filtered(
                lambda item: item.code == proposal_code
                and item.state in ("approved", "issued")
                and item.customer_issue_allowed
            )[:1]
            if not order_punch or not proposal or not sseries_case.order_punch_approved:
                raise ValidationError(_("Approved S-Series proposal and Order Punch evidence are required."))
        else:
            drive_pdf_pattern = re.compile(r"^https://drive\.google\.com/(?:file/d/|open\?id=)[A-Za-z0-9_-]+")
            if not drive_pdf_pattern.match((self.hjig_order_punch_pdf_url or "").strip()):
                raise ValidationError(_("Link the approved Order Punch PDF before programme activation."))
            if not drive_pdf_pattern.match((self.hjig_commercial_pdf_url or "").strip()):
                raise ValidationError(_("Link the approved Commercial PDF before programme activation."))
        if not project:
            project_values = {
                "name": "%s - %s" % (self.partner_id.name, version.template_id.name),
                "partner_id": self.partner_id.id,
                "company_id": self.company_id.id,
                "hjig_project_record_type": "customer",
                "x_project_code": project_code,
            }
            if programme_key:
                project_values["hjig_programme"] = programme_key
            project_fields = self.env["project.project"]._fields
            if "x_order_reference_id" in project_fields:
                project_values["x_order_reference_id"] = self.id
            project = self.env["project.project"].create(project_values)
        elif project.x_project_code != project_code:
            raise ValidationError(
                _("The approved Project Code does not match the existing order-linked project.")
            )
        run = self.env["hjig.programme.run"].create({
            "name": "%s / %s" % (project.x_project_code, version.name),
            "sale_order_id": self.id,
            "project_id": project.id,
            "template_version_id": version.id,
        })
        self.with_context(hjig_programme_activation=True).write({
            "hjig_project_code": project_code,
            "hjig_project_id": project.id,
            "hjig_programme_run_id": run.id,
        })
        run._ensure_scope_decisions()
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
    hjig_programme_activation_state = fields.Selection(
        [
            ("none", "Not Activated"),
            ("draft", "Setup Required"),
            ("generated", "Active Programme Run"),
            ("closed", "Closed"),
        ],
        compute="_compute_hjig_programme_activation_state",
        string="Programme Activation Status",
    )
    sourcebridge_engagement_ids = fields.One2many(
        "hjig.sourcebridge.engagement", "project_id", string="SourceBridge Engagements"
    )

    @api.depends("hjig_programme_run_ids")
    def _compute_hjig_programme_run_count(self):
        for project in self:
            project.hjig_programme_run_count = len(project.hjig_programme_run_ids)

    @api.depends("hjig_programme_run_ids.state")
    def _compute_hjig_programme_activation_state(self):
        for project in self:
            run = project.hjig_programme_run_ids[:1]
            project.hjig_programme_activation_state = run.state if run else "none"


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
    hjig_coordinator_designation_id = fields.Many2one(
        "hjig.governance.designation", ondelete="restrict", index=True, tracking=True
    )
    hjig_support_designation_ids = fields.Many2many(
        "hjig.governance.designation",
        "hjig_project_task_support_designation_rel",
        "task_id",
        "designation_id",
        string="Supporting Designations",
    )
    hjig_execution_basis = fields.Selection(
        [("project", "Project"), ("component", "Component"), ("mould", "Mould")],
        readonly=True,
        index=True,
        copy=False,
    )
    hjig_execution_scope_key = fields.Char(readonly=True, index=True, copy=False)
    hjig_mould_id = fields.Many2one(
        "x_mould", readonly=True, ondelete="restrict", index=True, copy=False
    )
    hjig_part_id = fields.Many2one(
        "x_mould_part", readonly=True, ondelete="restrict", index=True, copy=False
    )
    hjig_required_artifact_ids = fields.Many2many(
        related="hjig_template_activity_id.required_artifact_ids",
        string="Required SOPs / Forms",
        readonly=True,
    )
    hjig_open_predecessor_ids = fields.Many2many(
        "project.task",
        compute="_compute_hjig_execution_readiness",
        string="Open Predecessors",
    )
    hjig_missing_artifact_requirement_ids = fields.Many2many(
        "hjig.programme.run.artifact",
        compute="_compute_hjig_execution_readiness",
        string="Missing Approved Evidence",
    )
    hjig_execution_blocked = fields.Boolean(
        compute="_compute_hjig_execution_readiness",
        string="Execution Blocked",
    )
    hjig_execution_block_reason = fields.Text(
        compute="_compute_hjig_execution_readiness",
        string="Block Reason",
    )

    _programme_activity_unique = models.Constraint(
        "UNIQUE(hjig_programme_run_id, hjig_template_activity_id, hjig_execution_scope_key)",
        "A programme activity can generate only one task in the same governed execution scope.",
    )

    def _hjig_matching_artifact_requirements(self):
        """Return this activity's controlled evidence requirements in the same execution scope."""
        self.ensure_one()
        if not self.hjig_programme_run_id or not self.hjig_template_activity_id:
            return self.env["hjig.programme.run.artifact"]
        artifact_ids = self.hjig_required_artifact_ids.ids
        if not artifact_ids:
            return self.env["hjig.programme.run.artifact"]
        requirements = self.hjig_programme_run_id.artifact_requirement_ids.filtered(
            lambda item: item.stage_id == self.hjig_governance_stage_id
            and item.artifact_master_id.id in artifact_ids
        )
        if self.hjig_execution_basis in ("mould", "component"):
            return requirements.filtered(lambda item: item.mould_id == self.hjig_mould_id)
        return requirements.filtered(lambda item: not item.mould_id)

    @api.depends(
        "depend_on_ids.stage_id.fold",
        "hjig_programme_run_id.artifact_requirement_ids.status",
        "hjig_programme_run_id.artifact_requirement_ids.mould_id",
        "hjig_template_activity_id.required_artifact_ids",
        "hjig_governance_stage_id",
        "hjig_mould_id",
    )
    def _compute_hjig_execution_readiness(self):
        for task in self:
            if not task.hjig_programme_run_id:
                task.hjig_open_predecessor_ids = False
                task.hjig_missing_artifact_requirement_ids = False
                task.hjig_execution_blocked = False
                task.hjig_execution_block_reason = False
                continue
            open_predecessors = task.depend_on_ids.filtered(lambda item: not item.stage_id.fold)
            missing_evidence = task._hjig_matching_artifact_requirements().filtered(
                lambda item: item.mandatory and item.status != "approved"
            )
            reasons = []
            if open_predecessors:
                reasons.append(
                    _("Complete predecessor tasks: %s")
                    % ", ".join(open_predecessors.mapped("display_name"))
                )
            if missing_evidence:
                reasons.append(
                    _("Approve required evidence: %s")
                    % ", ".join(missing_evidence.mapped("artifact_master_id.display_name"))
                )
            task.hjig_open_predecessor_ids = open_predecessors
            task.hjig_missing_artifact_requirement_ids = missing_evidence
            task.hjig_execution_blocked = bool(reasons)
            task.hjig_execution_block_reason = "\n".join(reasons) or False

    def action_open_hjig_required_evidence(self):
        self.ensure_one()
        requirements = self._hjig_matching_artifact_requirements()
        return {
            "type": "ir.actions.act_window",
            "name": _("Required Evidence — %s") % self.display_name,
            "res_model": "hjig.programme.run.artifact",
            "view_mode": "list,form",
            "domain": [("id", "in", requirements.ids)],
            "context": {"create": False, "delete": False},
        }

    def _assert_hjig_stage_transition_ready(self, new_stage):
        for task in self.filtered("hjig_programme_run_id"):
            if new_stage == task.stage_id:
                continue
            open_predecessors = task.depend_on_ids.filtered(lambda item: not item.stage_id.fold)
            if open_predecessors:
                raise ValidationError(
                    _("This governed activity is locked until these predecessors are complete: %s")
                    % ", ".join(open_predecessors.mapped("display_name"))
                )
            if new_stage.fold:
                missing_evidence = task._hjig_matching_artifact_requirements().filtered(
                    lambda item: item.mandatory and item.status != "approved"
                )
                if missing_evidence:
                    raise ValidationError(
                        _("This activity cannot be completed until required evidence is approved: %s")
                        % ", ".join(missing_evidence.mapped("artifact_master_id.display_name"))
                    )

    @api.constrains(
        "hjig_programme_run_id", "hjig_template_activity_id", "hjig_execution_basis",
        "hjig_execution_scope_key", "hjig_mould_id", "hjig_part_id",
    )
    def _check_hjig_execution_scope(self):
        for task in self.filtered("hjig_programme_run_id"):
            activity = task.hjig_template_activity_id
            if task.hjig_execution_basis != activity.execution_basis:
                raise ValidationError(_("Generated task execution basis must match its template activity."))
            if task.hjig_execution_basis == "project":
                if task.hjig_execution_scope_key != "P" or task.hjig_mould_id or task.hjig_part_id:
                    raise ValidationError(_("A project-basis activity cannot carry a mould or component scope."))
            elif task.hjig_execution_basis == "mould":
                if not task.hjig_mould_id or task.hjig_part_id:
                    raise ValidationError(_("A mould-basis activity requires exactly one mould scope."))
            elif not task.hjig_part_id or task.hjig_part_id.x_mould_id != task.hjig_mould_id:
                raise ValidationError(_("A component-basis activity requires one component in its matching mould."))
            if task.hjig_mould_id and task.hjig_mould_id.x_project_id != task.project_id:
                raise ValidationError(_("Generated task mould scope must belong to the task project."))

    def write(self, vals):
        if "stage_id" in vals:
            new_stage = self.env["project.task.type"].browse(vals["stage_id"])
            self._assert_hjig_stage_transition_ready(new_stage)
        frozen = {
            "project_id", "hjig_programme_run_id", "hjig_template_activity_id", "hjig_governance_stage_id",
            "hjig_owner_designation_id", "hjig_approver_designation_id",
            "hjig_coordinator_designation_id", "hjig_support_designation_ids",
            "hjig_execution_basis", "hjig_execution_scope_key", "hjig_mould_id", "hjig_part_id",
            "depend_on_ids",
        }
        if frozen.intersection(vals) and not is_workflow_context(self.env) and self.filtered(
            lambda task: task.hjig_programme_run_id.state in ("generated", "closed")
        ):
            raise ValidationError(_("Generated task governance fields are frozen by the programme snapshot."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda task: task.hjig_programme_run_id.state in ("generated", "closed")):
            raise UserError(_("A generated programme activity task cannot be deleted."))
        return super().unlink()
