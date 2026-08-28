# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


class ProjectProject(models.Model):
    _inherit = "project.project"

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

    @api.model_create_multi
    def create(self, vals_list):
        if any("hjig_authorized_user_ids" in vals for vals in vals_list) and not self.env.user.has_group(
            "project.group_project_manager"
        ):
            raise UserError(_("Only Project Managers may assign the governed Hongyi project team."))
        return super().create(vals_list)

    def write(self, vals):
        if "hjig_authorized_user_ids" in vals and not self.env.user.has_group("project.group_project_manager"):
            raise UserError(_("Only Project Managers may change the governed Hongyi project team."))
        return super().write(vals)


class HjigTargetMixin(models.AbstractModel):
    _name = "hjig.target.mixin"
    _description = "Hongyi Governed Target Mixin"

    @api.model
    def _selection_target_model(self):
        """Modules extend this method when they add a governed operational model."""
        return [
            ("project.project", "Project"),
            ("project.task", "Project Task"),
            ("hjig.project.document", "Controlled Project Document"),
            ("hjig.baseline", "Controlled Baseline"),
            ("hjig.evidence.link", "Evidence"),
            ("hjig.approval", "Controlled Approval"),
        ]

    def _check_target_project(self, target_record, project):
        if target_record._name == "project.project":
            target_project = target_record
        else:
            target_project = target_record.project_id if "project_id" in target_record._fields else False
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
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver"):
            raise UserError(_("Only authorised Governance Approvers may verify evidence."))
        for evidence in self:
            if evidence.verification_state != "unverified":
                raise UserError(_("Only Unverified evidence can be accepted or rejected."))
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
            })

    def action_accept(self):
        self._record_verification("accepted")

    def action_reject(self):
        self._record_verification("rejected")

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
        workflow_fields = {"state", "approver_id", "decision_date", "requested_by_id", "requested_date"}
        if workflow_fields.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Approval audit fields may only change through decision actions."))
        if any(record.state != "pending" for record in self):
            protected = {
                "project_id", "target_ref", "approval_type", "authority_designation_id",
                "requested_by_id", "requested_date", "decision_reason",
            }
            if protected.intersection(vals):
                raise ValidationError(_("A completed approval is read-only."))
        return super().write(vals)

    def _check_decision_authority(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_governance_approver"):
            raise UserError(_("Only authorised Hongyi Governance Approvers may decide this request."))
        for approval in self:
            if approval.authority_designation_id and self.env.user not in approval.authority_designation_id.holder_ids:
                raise UserError(_("You do not hold the required approval designation."))
            if approval.requested_by_id == self.env.user:
                raise ValidationError(_("The requester cannot approve or reject their own request."))

    def _record_decision(self, state):
        self._check_decision_authority()
        for approval in self:
            if approval.state != "pending":
                raise UserError(_("Only Pending approvals can be decided."))
            if state == "rejected" and not (approval.decision_reason or "").strip():
                raise ValidationError(_("A rejection reason is required."))
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
                "reason": approval.decision_reason,
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
