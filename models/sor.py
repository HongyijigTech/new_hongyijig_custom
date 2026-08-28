# -*- coding: utf-8 -*-

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


INDUSTRY_SELECTION = [
    ("automotive", "Automotive"),
    ("medical", "Medical"),
    ("consumer_electronics", "Consumer Electronics"),
    ("home_appliances", "Home Appliances"),
]

PHASE_SELECTION = [
    ("concept", "Concept / Feasibility"),
    ("design", "Design"),
    ("prototype", "Prototype"),
    ("tooling", "Tooling / Manufacturing"),
    ("trial", "Trial"),
    ("final_sample", "Final Sample"),
    ("shipment", "Shipment"),
    ("installation", "Installation Support"),
    ("closure", "Closure"),
]


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [
            ("hjig.sor", "SOR"),
            ("hjig.sor.requirement", "SOR Requirement"),
        ]


class HjigSor(models.Model):
    _name = "hjig.sor"
    _description = "Hongyi Statement of Requirements"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    customer_id = fields.Many2one(related="project_id.partner_id", store=True, readonly=True)
    industry = fields.Selection(INDUSTRY_SELECTION, required=True, index=True, tracking=True)
    intake_route = fields.Selection(
        [
            ("customer_sor", "Route A — Customer SOR mapped to Hongyi structure"),
            ("hongyi_guided", "Route B — Hongyi guided SOR"),
        ],
        required=True,
        tracking=True,
    )
    title = fields.Char(required=True, tracking=True)
    revision = fields.Char(required=True, default="R00", tracking=True)
    source_reference = fields.Char(
        string="Customer SOR / Template Reference",
        help="Customer document number and revision for Route A, or the controlled Hongyi template reference for Route B.",
        tracking=True,
    )
    source_url = fields.Char(string="Source Document Link", tracking=True)
    source_attachment_ids = fields.Many2many(
        "ir.attachment", "hjig_sor_attachment_rel", "sor_id", "attachment_id", string="Source Documents"
    )
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    effective_date = fields.Date(tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("mapping", "Mapping / Clarification"),
            ("review", "Under Review"),
            ("frozen", "Frozen"),
            ("rejected", "Rejected"),
            ("superseded", "Superseded"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    requirement_ids = fields.One2many("hjig.sor.requirement", "sor_id", string="Requirements")
    requirement_count = fields.Integer(compute="_compute_requirement_summary")
    open_clarification_count = fields.Integer(compute="_compute_requirement_summary")
    baseline_id = fields.Many2one("hjig.baseline", readonly=True, copy=False, ondelete="restrict")
    no_product_warranty = fields.Boolean(
        string="No Product Warranty by Hongyi",
        default=True,
        required=True,
        readonly=True,
        help="Hongyi provides project/engineering services and contracted installation support, not product warranty.",
    )
    installation_support_scope = fields.Text(
        help="Record only the contracted installation-support scope. This field must not imply product warranty."
    )
    notes = fields.Text()

    _code_unique = models.Constraint("UNIQUE(code)", "SOR code must be unique.")
    _project_revision_unique = models.Constraint(
        "UNIQUE(project_id, industry, revision)", "This SOR revision already exists for the project and industry."
    )

    _LOCKED_FIELDS = {
        "project_id", "industry", "intake_route", "title", "revision", "source_reference",
        "source_url", "source_attachment_ids", "owner_id", "approval_authority_designation_id",
        "effective_date", "installation_support_scope", "notes",
    }

    @api.depends("requirement_ids", "requirement_ids.declaration_state")
    def _compute_requirement_summary(self):
        for sor in self:
            sor.requirement_count = len(sor.requirement_ids)
            sor.open_clarification_count = len(sor.requirement_ids.filtered(
                lambda requirement: requirement.declaration_state in ("unknown_recommendation", "pending")
            ))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            vals["no_product_warranty"] = True
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.sor") or _("New")
        return super().create(vals_list)

    @api.constrains("no_product_warranty")
    def _check_no_product_warranty(self):
        if any(not sor.no_product_warranty for sor in self):
            raise ValidationError(_("Hongyi SOR records cannot create or imply a product warranty."))

    @api.constrains("intake_route", "source_reference", "source_url", "source_attachment_ids")
    def _check_source_traceability(self):
        for sor in self:
            if sor.intake_route == "customer_sor":
                if not (sor.source_reference or "").strip():
                    raise ValidationError(_("Route A requires the customer SOR document number and revision."))
                if not sor.source_url and not sor.source_attachment_ids:
                    raise ValidationError(_("Route A requires the original customer SOR as a link or attachment."))

    def write(self, vals):
        if "state" in vals and not is_workflow_context(self.env):
            if any(record.state != vals["state"] for record in self):
                raise ValidationError(_("SOR state may only change through controlled workflow actions."))
        if "baseline_id" in vals and not is_workflow_context(self.env):
            raise ValidationError(_("The SOR baseline is controlled by the approval workflow."))
        if self._LOCKED_FIELDS.intersection(vals) and any(
            record.state in ("frozen", "superseded") for record in self
        ):
            raise ValidationError(_("Frozen or superseded SOR records are read-only. Create a new revision."))
        if "no_product_warranty" in vals:
            vals["no_product_warranty"] = True
        return super().write(vals)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only Draft SOR records may be deleted."))
        return super().unlink()

    def action_start_mapping(self):
        for sor in self:
            if sor.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected SOR records can enter mapping."))
            previous_state = sor.state
            sor.with_context(**workflow_context()).write({"state": "mapping"})
            sor._log_transition(previous_state, "mapping", "mapping_started")

    def _check_ready_for_review(self):
        for sor in self:
            if not sor.requirement_ids:
                raise ValidationError(_("At least one SOR requirement is required."))
            if not sor.effective_date:
                raise ValidationError(_("Effective Date is required before SOR review."))
            for requirement in sor.requirement_ids:
                requirement._check_review_readiness()

    def action_submit_review(self):
        self._check_ready_for_review()
        for sor in self:
            if sor.state not in ("draft", "mapping", "rejected"):
                raise UserError(_("Only Draft, Mapping, or Rejected SOR records can be submitted."))
            previous_state = sor.state
            baseline = sor.baseline_id
            if not baseline:
                baseline = self.env["hjig.baseline"].create({
                    "project_id": sor.project_id.id,
                    "target_ref": "%s,%s" % (sor._name, sor.id),
                    "baseline_type": "sor",
                    "revision": sor.revision,
                    "effective_date": sor.effective_date,
                    "change_reason": "SOR freeze request %s" % sor.code,
                    "approval_authority_designation_id": sor.approval_authority_designation_id.id,
                })
            elif baseline.state != "rejected":
                raise ValidationError(_("Existing SOR baseline is not available for resubmission."))
            baseline.action_submit_review()
            sor.with_context(**workflow_context()).write({
                "state": "review", "baseline_id": baseline.id,
            })
            sor._log_transition(previous_state, "review", "submitted", baseline.approval_id)

    def action_apply_decision(self):
        for sor in self:
            if sor.state != "review" or not sor.baseline_id:
                raise UserError(_("The SOR has no approval decision to apply."))
            sor.baseline_id.action_apply_approval()
            if sor.baseline_id.state == "approved":
                next_state = "frozen"
            elif sor.baseline_id.state == "rejected":
                next_state = "rejected"
            else:
                raise UserError(_("The SOR approval is still pending."))
            sor.with_context(**workflow_context()).write({"state": next_state})
            sor._log_transition("review", next_state, sor.baseline_id.approval_id.state, sor.baseline_id.approval_id)

    def _log_transition(self, from_state, to_state, decision, approval=False):
        self.ensure_one()
        self.env["hjig.transition.log"].sudo().create({
            "project_id": self.project_id.id,
            "target_ref": "%s,%s" % (self._name, self.id),
            "from_state": from_state,
            "to_state": to_state,
            "decision": decision,
            "actor_id": self.env.user.id,
            "approval_id": approval.id if approval else False,
        })


class HjigSorRequirement(models.Model):
    _name = "hjig.sor.requirement"
    _description = "Hongyi SOR Requirement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sor_id, sequence, id"
    _rec_name = "requirement_id"

    sequence = fields.Integer(default=10)
    sor_id = fields.Many2one("hjig.sor", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="sor_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="sor_id.company_id", store=True, readonly=True, index=True)
    requirement_id = fields.Char(required=True, index=True, tracking=True)
    category = fields.Selection(
        [
            ("scope", "Scope / Deliverable"),
            ("technical", "Technical"),
            ("quality", "Quality / Acceptance"),
            ("commercial", "Commercial Boundary"),
            ("responsibility", "Responsibility"),
            ("documentation", "Documentation / Evidence"),
            ("logistics", "Logistics / Installation Support"),
        ],
        required=True,
        tracking=True,
    )
    requirement_text = fields.Text(required=True, tracking=True)
    declaration_state = fields.Selection(
        [
            ("specified", "Specified"),
            ("not_applicable", "Not Applicable"),
            ("unknown_recommendation", "Unknown — Hongyi Recommendation Required"),
            ("pending", "Pending — Customer Clarification Required"),
        ],
        required=True,
        tracking=True,
        help="Blank is not an allowed requirement state.",
    )
    source_reference = fields.Char(string="Source Clause / Page", tracking=True)
    acceptance_criteria = fields.Text(tracking=True)
    priority = fields.Selection(
        [("critical", "Critical"), ("high", "High"), ("normal", "Normal"), ("low", "Low")],
        default="normal",
        required=True,
        tracking=True,
    )
    owner_id = fields.Many2one("res.users", tracking=True)
    clarification_due_date = fields.Date(tracking=True)
    verification_ids = fields.One2many(
        "hjig.sor.requirement.verification", "requirement_id", string="Phase Verification"
    )
    notes = fields.Text()

    _sor_requirement_unique = models.Constraint(
        "UNIQUE(sor_id, requirement_id)", "Requirement ID must be unique within the SOR."
    )

    @api.constrains("sor_id")
    def _check_sor_not_frozen(self):
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise ValidationError(_("Requirements cannot be added after SOR review begins."))

    def write(self, vals):
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise ValidationError(_("Requirements are read-only after SOR review begins."))
        return super().write(vals)

    def unlink(self):
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise UserError(_("Requirements cannot be deleted after SOR review begins."))
        return super().unlink()

    def _check_review_readiness(self):
        self.ensure_one()
        if self.declaration_state == "specified":
            if not (self.acceptance_criteria or "").strip():
                raise ValidationError(_("Specified requirement %s needs acceptance criteria.") % self.requirement_id)
            if not self.verification_ids.filtered("check_required"):
                raise ValidationError(_("Specified requirement %s must be allocated to at least one phase.") % self.requirement_id)
        if self.sor_id.intake_route == "customer_sor" and not (self.source_reference or "").strip():
            raise ValidationError(_("Route A requirement %s needs its customer source clause/page.") % self.requirement_id)
        if self.declaration_state in ("unknown_recommendation", "pending"):
            if not self.owner_id or not self.clarification_due_date:
                raise ValidationError(_("Open requirement %s needs an owner and clarification due date.") % self.requirement_id)


class HjigSorRequirementVerification(models.Model):
    _name = "hjig.sor.requirement.verification"
    _description = "SOR Requirement Phase Verification"
    _order = "requirement_id, phase"

    requirement_id = fields.Many2one("hjig.sor.requirement", required=True, ondelete="cascade", index=True)
    sor_id = fields.Many2one(related="requirement_id.sor_id", store=True, readonly=True, index=True)
    project_id = fields.Many2one(related="requirement_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="requirement_id.company_id", store=True, readonly=True, index=True)
    phase = fields.Selection(PHASE_SELECTION, required=True, index=True)
    check_required = fields.Boolean(default=True, required=True)
    verification_method = fields.Char(required=True)
    required_evidence = fields.Char(required=True)
    responsible_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    due_date = fields.Date()
    status = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("waived", "Waived")],
        default="pending",
        required=True,
        tracking=True,
    )
    evidence_ids = fields.Many2many(
        "hjig.evidence.link", "hjig_sor_verification_evidence_rel", "verification_id", "evidence_id", string="Evidence"
    )
    verified_by_id = fields.Many2one("res.users", readonly=True)
    verified_date = fields.Datetime(readonly=True)
    cycle = fields.Integer(default=1, required=True, readonly=True)
    reverification_reason = fields.Text(help="Required to reopen a failed phase verification.")
    audit_history_json = fields.Text(
        string="Immutable Verification History", default="[]", readonly=True, copy=False,
        help="Server-controlled snapshot of every completed phase-verification cycle and its evidence.",
    )
    notes = fields.Text()

    _requirement_phase_unique = models.Constraint(
        "UNIQUE(requirement_id, phase)", "A requirement can have only one verification row per phase."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            controlled = {
                "status": "pending", "verified_by_id": False,
                "verified_date": False, "cycle": 1, "audit_history_json": "[]",
            }
            for field_name, default_value in controlled.items():
                if field_name in vals and vals[field_name] not in (False, default_value):
                    raise ValidationError(_("Verification result-control fields cannot be supplied during creation."))
            vals.update(controlled)
            requirement = self.env["hjig.sor.requirement"].browse(vals.get("requirement_id")).exists()
            if requirement and requirement.sor_id.state in ("review", "frozen", "superseded"):
                raise ValidationError(_("Phase allocations cannot be added after SOR review begins."))
        return super().create(vals_list)

    @api.constrains("requirement_id", "evidence_ids")
    def _check_verification_governance(self):
        for verification in self:
            if any(evidence.project_id != verification.project_id for evidence in verification.evidence_ids):
                raise ValidationError(_("Verification evidence must belong to the same project."))

    def write(self, vals):
        if any(record.sor_id.state == "review" for record in self):
            raise ValidationError(_("Phase allocations are read-only while the SOR is under review."))
        if any(record.sor_id.state in ("frozen", "superseded") for record in self):
            allowed = {
                "status", "evidence_ids", "verified_by_id", "verified_date",
                "cycle", "reverification_reason", "notes", "audit_history_json",
            }
            if set(vals) - allowed:
                raise ValidationError(_("The phase allocation is locked after SOR freeze."))
        if "evidence_ids" in vals and any(record.status != "pending" for record in self) and not is_workflow_context(self.env):
            raise ValidationError(_("Recorded SOR verification evidence is locked. Reopen a failed result for controlled re-verification."))
        workflow_fields = {"status", "verified_by_id", "verified_date", "cycle", "audit_history_json"}
        if workflow_fields.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Verification status may only change through verification actions."))
        return super().write(vals)

    def unlink(self):
        if any(record.sor_id.state in ("review", "frozen", "superseded") for record in self):
            raise UserError(_("Phase allocations cannot be deleted after SOR review begins."))
        return super().unlink()

    def action_pass(self):
        self._record_result("pass")

    def action_fail(self):
        self._record_result("fail")

    def action_reopen_failed(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver"):
            raise UserError(_("Only an authorised Governance Approver may reopen a failed SOR verification."))
        for verification in self:
            if verification.sor_id.state != "frozen":
                raise UserError(_("Only a verification on the current Frozen SOR may be reopened."))
            if self.env.user not in verification.responsible_designation_id.holder_ids:
                raise UserError(_("Only a holder of the responsible designation may reopen this verification."))
            if verification.status != "fail":
                raise UserError(_("Only a Failed SOR verification can be reopened."))
            if not (verification.reverification_reason or "").strip():
                raise ValidationError(_("A re-verification reason is required."))
            reverification_reason = verification.reverification_reason
            history = json.loads(verification.audit_history_json or "[]")
            if not history or history[-1].get("cycle") != verification.cycle:
                raise ValidationError(_("The recorded SOR verification has no immutable cycle snapshot."))
            history[-1].update({
                "reopened_by_id": self.env.user.id,
                "reopened_date": fields.Datetime.to_string(fields.Datetime.now()),
                "reverification_reason": reverification_reason,
            })
            verification.with_context(**workflow_context()).write({
                "status": "pending", "cycle": verification.cycle + 1,
                "verified_by_id": False, "verified_date": False,
                "reverification_reason": False,
                "audit_history_json": json.dumps(history, sort_keys=True),
            })
            self.env["hjig.transition.log"].sudo().create({
                "project_id": verification.project_id.id,
                "target_ref": "%s,%s" % (verification.requirement_id._name, verification.requirement_id.id),
                "from_state": "fail", "to_state": "pending",
                "decision": "reverification_requested", "actor_id": self.env.user.id,
                "reason": reverification_reason,
            })

    def _record_result(self, result):
        for verification in self:
            if verification.status != "pending":
                raise UserError(_("Only Pending requirement verifications can be decided."))
            if verification.sor_id.state != "frozen":
                raise UserError(_("Requirement verification starts only after the SOR is Frozen."))
            if self.env.user not in verification.responsible_designation_id.holder_ids:
                raise UserError(_("Only a holder of the responsible designation may verify this requirement."))
            if not verification.check_required:
                raise UserError(_("This phase is not marked for verification."))
            if not verification.evidence_ids:
                raise ValidationError(_("Accepted evidence is required before a phase verification can record PASS or FAIL."))
            verification.evidence_ids._assert_accepted()
            verified_date = fields.Datetime.now()
            history = json.loads(verification.audit_history_json or "[]")
            history.append({
                "cycle": verification.cycle,
                "result": result,
                "evidence": [
                    {"id": evidence.id, "code": evidence.code}
                    for evidence in verification.evidence_ids
                ],
                "verified_by_id": self.env.user.id,
                "verified_date": fields.Datetime.to_string(verified_date),
                "notes": verification.notes or "",
            })
            verification.with_context(**workflow_context()).write({
                "status": result,
                "verified_by_id": self.env.user.id,
                "verified_date": verified_date,
                "audit_history_json": json.dumps(history, sort_keys=True),
            })
            self.env["hjig.transition.log"].sudo().create({
                "project_id": verification.project_id.id,
                "target_ref": "%s,%s" % (verification.requirement_id._name, verification.requirement_id.id),
                "from_state": "pending", "to_state": result, "decision": result,
                "actor_id": self.env.user.id,
            })
