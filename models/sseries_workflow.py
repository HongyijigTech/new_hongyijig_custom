import base64
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PROGRAMME_ROUTES = [
    ("launchguard_complete", "LaunchGuard Complete"),
    ("launchguard_design", "LaunchGuard Design"),
    ("launchguard_development", "LaunchGuard Development"),
    ("toollock_control", "ToolLock Control"),
    ("toollock_lite", "ToolLock Lite"),
    ("sourcebridge_only", "SourceBridge Only"),
]

ROUTE_PROPOSAL_TEMPLATE = {
    "launchguard_complete": "LGC-03",
    "launchguard_design": "LGD-03",
    "launchguard_development": "LGV-03",
    "toollock_control": "TLC-03",
    "toollock_lite": "TLL-03",
    "sourcebridge_only": "SB-03",
}

ROUTE_PROPOSAL_SEQUENCE = {
    "launchguard_complete": "hjig.sseries.proposal.lgc",
    "launchguard_design": "hjig.sseries.proposal.lgd",
    "launchguard_development": "hjig.sseries.proposal.lgv",
    "toollock_control": "hjig.sseries.proposal.tlc",
    "toollock_lite": "hjig.sseries.proposal.tll",
    "sourcebridge_only": "hjig.sseries.proposal.sbg",
}

ROUTE_PROGRAMME_TEMPLATE = {
    "launchguard_complete": "LGC",
    "launchguard_design": "LGD",
    "launchguard_development": "LGV",
    "toollock_control": "TLC",
    "toollock_lite": "TLL",
}

ROUTE_PROJECT_SEQUENCE = {
    "launchguard_complete": "hjig.sseries.project.lgc",
    "launchguard_design": "hjig.sseries.project.lgd",
    "launchguard_development": "hjig.sseries.project.lgv",
    "toollock_control": "hjig.sseries.project.tlc",
    "toollock_lite": "hjig.sseries.project.tll",
    "sourcebridge_only": "hjig.sseries.project.sbg",
}


class HjigSSeriesDocumentTemplate(models.Model):
    _name = "hjig.sseries.document.template"
    _description = "Controlled S-Series Document Template Authority"
    _order = "stage, code"

    code = fields.Char(required=True, readonly=True, index=True)
    name = fields.Char(required=True, readonly=True)
    stage = fields.Selection(
        [
            ("s0_received", "S0 Submission"),
            ("s1_review", "S1 Internal Review"),
            ("s2_assessment", "S2 Governance"),
            ("s3_proposal", "S3 Commercial"),
            ("s4_activation", "S4 Activation"),
            ("s5_sourcing", "S5 Sourcing"),
            ("s6_handover", "S6 Handover"),
            ("b0_released", "B0 Manifest"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    audience = fields.Selection(
        [
            ("internal", "Internal Only"),
            ("customer", "Customer Controlled"),
            ("supplier", "Supplier Controlled"),
        ],
        required=True,
        readonly=True,
    )
    master_file_id = fields.Char(readonly=True)
    visual_parent_code = fields.Char(readonly=True)
    source_sha256 = fields.Char(readonly=True)
    rule_set_id = fields.Char(required=True, readonly=True, default="HJIG-DOC-GOV-LOCK-v1.1")
    requires_file = fields.Boolean(default=True, readonly=True)
    rendering_status = fields.Selection(
        [
            ("ready", "Master Resolved"),
            ("template_state", "Template State Only"),
            ("blocked", "Fail-Closed / Unresolved"),
        ],
        required=True,
        readonly=True,
        default="blocked",
    )
    template_visual_qa_verified = fields.Boolean(readonly=True)
    template_content_qa_verified = fields.Boolean(readonly=True)
    user_final_approval = fields.Boolean(readonly=True)
    customer_issue_allowed = fields.Boolean(readonly=True)
    supplier_issue_allowed = fields.Boolean(readonly=True)
    active = fields.Boolean(default=True, readonly=True)
    notes = fields.Text(readonly=True)

    _code_unique = models.Constraint("UNIQUE(code)", "S-Series document template code must be unique.")

    def write(self, vals):
        if not self.env.context.get("install_mode"):
            raise UserError(_("Controlled S-Series template authority is changed only by a versioned module release."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Controlled S-Series template authority cannot be deleted."))


class HjigSSeriesArtifact(models.Model):
    _name = "hjig.sseries.artifact"
    _description = "Governed S-Series Document Candidate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "case_id, stage, id"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    case_id = fields.Many2one("hjig.sseries.case", required=True, ondelete="restrict", index=True)
    template_id = fields.Many2one(
        "hjig.sseries.document.template", required=True, ondelete="restrict", index=True
    )
    code = fields.Char(related="template_id.code", store=True, readonly=True, index=True)
    stage = fields.Selection(related="template_id.stage", store=True, readonly=True, index=True)
    audience = fields.Selection(related="template_id.audience", store=True, readonly=True)
    version = fields.Integer(default=1, required=True, readonly=True)
    state = fields.Selection(
        [
            ("required", "Required"),
            ("draft", "Draft Attached"),
            ("qa_verified", "QA Verified"),
            ("approved", "Approved"),
            ("issued", "Issued"),
            ("blocked", "Blocked"),
        ],
        required=True,
        default="required",
        tracking=True,
        index=True,
    )
    document_data = fields.Binary(attachment=True)
    document_filename = fields.Char()
    document_sha256 = fields.Char(readonly=True, copy=False, index=True)
    prepared_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    visual_qa_verified = fields.Boolean(readonly=True, tracking=True)
    content_qa_verified = fields.Boolean(readonly=True, tracking=True)
    user_final_approval = fields.Boolean(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    customer_issue_allowed = fields.Boolean(readonly=True, tracking=True)
    supplier_issue_allowed = fields.Boolean(readonly=True, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    issued_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    issued_on = fields.Datetime(readonly=True, copy=False)
    issue_reference = fields.Char(
        copy=False, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    company_id = fields.Many2one(related="case_id.company_id", store=True, readonly=True)

    _case_template_version_unique = models.Constraint(
        "UNIQUE(case_id, template_id, version)",
        "A document template version can appear only once in an S-Series case.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hjig_sseries_workflow"):
            raise UserError(_("S-Series document requirements are created only by governed workflow actions."))
        return super().create(vals_list)

    def write(self, vals):
        frozen = {"name", "case_id", "template_id", "version"}
        if frozen.intersection(vals):
            raise ValidationError(_("S-Series document provenance is immutable."))
        if "document_sha256" in vals and not self.env.context.get("hjig_sseries_artifact_workflow"):
            raise ValidationError(_("Document hash is recorded only by governed QA verification."))
        if {"state", "visual_qa_verified", "content_qa_verified", "customer_issue_allowed",
            "supplier_issue_allowed", "approved_by_id", "approved_on", "issued_by_id",
            "issued_on", "issue_reference"}.intersection(vals) and not self.env.context.get(
                "hjig_sseries_artifact_workflow"
            ):
            raise ValidationError(_("Use governed document actions to change QA, approval or issue state."))
        if self.filtered(lambda item: item.state in ("approved", "issued")) and {
            "document_data", "document_filename"
        }.intersection(vals):
            raise ValidationError(_("An approved S-Series document binary cannot be replaced."))
        if "document_data" in vals and not self.env.context.get("hjig_sseries_artifact_workflow"):
            vals["prepared_by_id"] = self.env.user.id
            vals["state"] = "draft" if vals.get("document_data") else "required"
        return super().write(vals)

    def unlink(self):
        raise UserError(_("S-Series document requirements cannot be deleted."))

    def action_verify_qa(self):
        self._assert_manager()
        for artifact in self:
            if artifact.template_id.rendering_status == "blocked":
                raise ValidationError(_("The exact approved master is unresolved; QA must fail closed."))
            if artifact.template_id.requires_file and not artifact.document_data:
                raise ValidationError(_("Attach the rendered candidate before QA verification."))
            digest = False
            if artifact.document_data:
                try:
                    raw = base64.b64decode(artifact.document_data, validate=True)
                except Exception as error:
                    raise ValidationError(_("The attached document cannot be decoded.")) from error
                if not raw.startswith(b"%PDF-"):
                    raise ValidationError(_("The governed candidate must be a physical PDF."))
                digest = hashlib.sha256(raw).hexdigest()
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "state": "qa_verified",
                "document_sha256": digest,
                "visual_qa_verified": True,
                "content_qa_verified": True,
                "customer_issue_allowed": False,
                "supplier_issue_allowed": False,
            })
        return True

    def action_approve(self):
        self._assert_manager()
        for artifact in self:
            if artifact.state != "qa_verified":
                raise ValidationError(_("Visual and content QA must be verified before document approval."))
            if not artifact.prepared_by_id or artifact.prepared_by_id == self.env.user:
                raise ValidationError(_("Document preparer and approver must be different users."))
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
            })
        return True

    def action_allow_customer_issue(self):
        self._assert_manager()
        for artifact in self:
            if artifact.audience != "customer":
                raise ValidationError(_("Customer issue permission applies only to customer-controlled documents."))
            if artifact.state != "approved" or not artifact.user_final_approval:
                raise ValidationError(_("Approved output and explicit user final approval are required."))
            if artifact.template_id.rendering_status != "ready":
                raise ValidationError(_("Customer issue is blocked until the exact master renderer is verified."))
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "customer_issue_allowed": True,
            })
        return True

    def action_allow_supplier_issue(self):
        self._assert_manager()
        for artifact in self:
            if artifact.audience != "supplier":
                raise ValidationError(_("Supplier issue permission applies only to supplier-controlled documents."))
            if artifact.state != "approved" or not artifact.user_final_approval:
                raise ValidationError(_("Approved output and explicit user final approval are required."))
            if artifact.template_id.rendering_status != "ready":
                raise ValidationError(_("Supplier issue is blocked until the exact master renderer is verified."))
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "supplier_issue_allowed": True,
            })
        return True

    def action_record_issue(self):
        self._assert_manager()
        for artifact in self:
            permitted = (
                artifact.audience == "customer" and artifact.customer_issue_allowed
            ) or (
                artifact.audience == "supplier" and artifact.supplier_issue_allowed
            )
            if artifact.audience == "internal" or not permitted:
                raise ValidationError(_("This document has no governed external issue permission."))
            if not (artifact.issue_reference or "").strip():
                raise ValidationError(_("Record the external issue evidence reference first."))
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "state": "issued",
                "issued_by_id": self.env.user.id,
                "issued_on": fields.Datetime.now(),
            })
        return True

    def _assert_manager(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
            raise UserError(_("S-Series Manager authority is required."))


class HjigSSeriesIntakeSubmission(models.Model):
    _inherit = "hjig.sseries.intake.submission"

    acknowledgement_state = fields.Selection(
        [("pending", "Pending"), ("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")],
        default="pending",
        required=True,
        readonly=True,
        copy=False,
    )
    acknowledgement_sent_on = fields.Datetime(readonly=True, copy=False)
    acknowledgement_mail_id = fields.Many2one("mail.mail", readonly=True, copy=False, ondelete="set null")

    @api.model
    def ingest_payload(self, payload, signature_timestamp=None):
        result = super().ingest_payload(payload, signature_timestamp=signature_timestamp)
        if not result["idempotent"]:
            result["submission"]._queue_acknowledgement_if_enabled()
        return result

    def _portfolio_acknowledgement_summary(self):
        self.ensure_one()
        projects = self.project_ids.sorted(lambda item: (item.sequence, item.id))
        items = "".join("<li>%s</li>" % project.name for project in projects)
        sourcing_count = len(projects.filtered("sourcebridge_selected"))
        sourcing_note = (
            "<p>SourceBridge sourcing information was received for %s project(s).</p>" % sourcing_count
            if sourcing_count else ""
        )
        return "<ul>%s</ul>%s" % (items, sourcing_note)

    def _queue_acknowledgement_if_enabled(self):
        mode = self.env["ir.config_parameter"].sudo().get_param(
            "hjig.sseries.acknowledgement_mode", "off"
        )
        if mode not in ("queue", "send"):
            return False
        sender = self.env["ir.config_parameter"].sudo().get_param(
            "hjig.sseries.acknowledgement_sender",
            "Business Development Team <businesscrm@hongyijiig.com>",
        )
        for submission in self.filtered(lambda item: item.acknowledgement_state == "pending"):
            mail = self.env["mail.mail"].sudo().create({
                "subject": _("Hongyi JIG submission received - %s") % submission.client_submission_id,
                "email_from": sender,
                "email_to": submission.customer_email,
                "reply_to": "businesscrm@hongyijiig.com",
                "body_html": """
                    <p>Dear %s,</p>
                    <p>Thank you. Hongyi JIG has received your submission under reference <strong>%s</strong>.</p>
                    <p>The following project portfolio information was received:</p>
                    %s
                    <p>This acknowledgement confirms receipt only. Programme route, scope, pricing and eligibility remain subject to Hongyi internal review.</p>
                    <p>Regards,<br/>Business Development Team<br/>Hongyi JIG</p>
                """ % (submission.contact_name, submission.client_submission_id,
                       submission._portfolio_acknowledgement_summary()),
                "auto_delete": False,
            })
            submission.with_context(hjig_sseries_ack=True).write({
                "acknowledgement_state": "queued",
                "acknowledgement_mail_id": mail.id,
            })
            if mode == "send":
                mail.send(raise_exception=True)
                submission.with_context(hjig_sseries_ack=True).write({
                    "acknowledgement_state": "sent",
                    "acknowledgement_sent_on": fields.Datetime.now(),
                })
        return True

    def write(self, vals):
        if set(vals).issubset({"acknowledgement_state", "acknowledgement_sent_on", "acknowledgement_mail_id"}) \
                and self.env.context.get("hjig_sseries_ack"):
            return models.Model.write(self, vals)
        return super().write(vals)


class HjigSSeriesCase(models.Model):
    _inherit = "hjig.sseries.case"

    programme_route = fields.Selection(PROGRAMME_ROUTES, tracking=True)
    scope_confirmed = fields.Boolean(tracking=True)
    internal_review_summary = fields.Text(tracking=True)
    internal_review_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    internal_review_approved_on = fields.Datetime(readonly=True, copy=False)
    governance_decision = fields.Selection(
        [("go", "GO"), ("hold", "HOLD"), ("no_go", "NO-GO")], tracking=True
    )
    risk_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")], tracking=True
    )
    governance_summary = fields.Text(tracking=True)
    governance_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    governance_approved_on = fields.Datetime(readonly=True, copy=False)
    approved_governance_fee = fields.Monetary(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    target_margin = fields.Float(
        default=0.35, tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    costing_rule_version = fields.Char(default="ODOO-MANAGER-APPROVED-FEE-v1", readonly=True)
    pricing_snapshot_json = fields.Json(
        readonly=True, copy=False, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    commercial_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    commercial_approved_on = fields.Datetime(readonly=True, copy=False)
    proposal_number = fields.Char(readonly=True, copy=False, index=True)
    proposal_version = fields.Integer(default=1, readonly=True)
    payment_terms_summary = fields.Text(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    nda_required = fields.Boolean(tracking=True)
    nda_completed = fields.Boolean(tracking=True)
    acceptance_basis = fields.Selection(
        [("signed_proposal", "Signed Proposal"), ("purchase_order", "Purchase Order")], tracking=True
    )
    customer_signature_received = fields.Boolean(tracking=True)
    hongyi_countersigned = fields.Boolean(tracking=True)
    purchase_order_received = fields.Boolean(tracking=True)
    acceptance_reference = fields.Char(tracking=True)
    acceptance_date = fields.Date(tracking=True)
    order_number = fields.Char(readonly=True, copy=False, index=True)
    order_punch_approved = fields.Boolean(readonly=True, tracking=True)
    proforma_reference = fields.Char(tracking=True)
    finance_approved = fields.Boolean(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    payment_received = fields.Boolean(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    payment_evidence_reference = fields.Char(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    tax_invoice_reference = fields.Char(
        tracking=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    handover_owner_id = fields.Many2one("res.users", domain="[('share', '=', False)]", tracking=True)
    handover_accepted = fields.Boolean(tracking=True)
    artifact_ids = fields.One2many("hjig.sseries.artifact", "case_id", readonly=True)
    b0_manifest_id = fields.Many2one("hjig.sseries.b0.handover", readonly=True, copy=False)
    portfolio_guard_id = fields.Many2one(
        "hjig.portfolio.guard", readonly=True, copy=False, ondelete="restrict"
    )
    portfolio_commercial_lead = fields.Boolean(compute="_compute_portfolio_summary")
    portfolio_case_count = fields.Integer(compute="_compute_portfolio_summary")
    sourcebridge_engagement_id = fields.Many2one(
        "hjig.sourcebridge.engagement", readonly=True, copy=False, ondelete="restrict"
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )

    def _assert_manager(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
            raise UserError(_("S-Series Manager authority is required."))

    @api.depends("submission_id", "form_type")
    def _compute_portfolio_summary(self):
        for case in self:
            cases = case.submission_id.case_ids.filtered(lambda item: item.stage != "cancelled").sorted("id")
            case.portfolio_case_count = len(cases) if case.form_type == "portfolio_guard" else 1
            case.portfolio_commercial_lead = bool(
                case.form_type != "portfolio_guard" or (cases and cases[0] == case)
            )

    def _portfolio_cases(self):
        self.ensure_one()
        if self.form_type != "portfolio_guard":
            return self
        return self.submission_id.case_ids.filtered(lambda item: item.stage != "cancelled").sorted("id")

    def _commercial_authority_case(self):
        self.ensure_one()
        return self._portfolio_cases()[:1]

    def _assert_commercial_authority(self):
        self.ensure_one()
        authority = self._commercial_authority_case()
        if authority != self:
            raise UserError(_(
                "PortfolioGuard has one umbrella commercial record. Open %s to run commercial and activation actions."
            ) % authority.display_name)
        return authority

    def write(self, vals):
        if not self.env.context.get("hjig_sseries_workflow"):
            workflow_fields = {
                "internal_review_approved_by_id", "internal_review_approved_on",
                "governance_approved_by_id", "governance_approved_on",
                "pricing_snapshot_json", "commercial_approved_by_id", "commercial_approved_on",
                "proposal_number", "proposal_version", "order_number", "order_punch_approved",
                "b0_manifest_id", "sourcebridge_engagement_id", "portfolio_guard_id",
            }
            if workflow_fields.intersection(vals):
                raise ValidationError(_("Governed workflow evidence can be written only by S-Series actions."))
            review_fields = {"programme_route", "scope_confirmed", "internal_review_summary", "reviewer_id"}
            governance_fields = {"governance_decision", "risk_level", "governance_summary"}
            commercial_fields = {"approved_governance_fee", "target_margin", "payment_terms_summary"}
            acceptance_fields = {
                "nda_required", "nda_completed", "acceptance_basis", "acceptance_reference", "acceptance_date",
                "customer_signature_received", "hongyi_countersigned", "purchase_order_received",
            }
            activation_fields = {
                "proforma_reference", "finance_approved", "payment_received",
                "payment_evidence_reference", "tax_invoice_reference",
            }
            handover_fields = {"handover_owner_id", "handover_accepted"}
            for case in self:
                if case.stage not in ("s0_received", "s1_review") and review_fields.intersection(vals):
                    raise ValidationError(_("Internal review inputs are frozen after S1 approval."))
                if case.stage not in ("s0_received", "s1_review", "s2_assessment") \
                        and governance_fields.intersection(vals):
                    raise ValidationError(_("Governance inputs are frozen after S2 approval."))
                if case.pricing_snapshot_json and commercial_fields.intersection(vals):
                    raise ValidationError(_("The approved pricing snapshot is immutable; create a controlled revision."))
                if case.stage not in ("s3_proposal", "s4_activation") \
                        and acceptance_fields.intersection(vals):
                    raise ValidationError(_("Acceptance evidence is frozen after activation."))
                if case.stage not in ("s4_activation",) and activation_fields.intersection(vals):
                    raise ValidationError(_("Finance and payment evidence is editable only during activation."))
                if case.stage not in ("s5_sourcing", "s6_handover") and handover_fields.intersection(vals):
                    raise ValidationError(_("Team handover fields are editable only before B0 release."))
                if case.stage == "b0_released" and set(vals) - {
                    "message_follower_ids", "message_partner_ids", "activity_ids"
                }:
                    raise ValidationError(_("A B0-released S-Series case is frozen."))
        return super().write(vals)

    def _ensure_customer_records(self):
        Partner = self.env["res.partner"].sudo()
        Lead = self.env["crm.lead"].sudo()
        for case in self:
            if not case.partner_id:
                partner = Partner.search([
                    ("email", "=ilike", case.submission_id.customer_email),
                    ("is_company", "=", True),
                ], limit=1)
                if not partner:
                    partner = Partner.create({
                        "name": case.customer_name,
                        "is_company": True,
                        "email": case.submission_id.customer_email,
                        "phone": case.submission_id.customer_mobile,
                    })
                case.partner_id = partner.id
            if not case.lead_id:
                case.lead_id = Lead.create({
                    "name": "%s - %s" % (case.customer_name, case.project_name),
                    "partner_id": case.partner_id.id,
                    "email_from": case.submission_id.customer_email,
                    "type": "opportunity",
                    "company_id": case.company_id.id,
                }).id

    def action_start_internal_review(self):
        result = super().action_start_internal_review()
        self._ensure_customer_records()
        self._ensure_artifact_codes(["S0-SUBMISSION", "S1-INTERNAL-REVIEW"])
        return result

    def _ensure_artifact_codes(self, codes):
        Template = self.env["hjig.sseries.document.template"]
        Artifact = self.env["hjig.sseries.artifact"].sudo().with_context(
            hjig_sseries_workflow=True
        )
        for case in self:
            templates = Template.search([("code", "in", list(dict.fromkeys(codes))), ("active", "=", True)])
            missing_codes = set(codes) - set(templates.mapped("code"))
            if missing_codes:
                raise ValidationError(_("Controlled document authority is missing: %s") % ", ".join(sorted(missing_codes)))
            existing = set(case.artifact_ids.mapped("template_id").ids)
            for template in templates.sorted(lambda item: (item.stage, item.code)):
                if template.id not in existing:
                    Artifact.create({
                        "name": "%s / %s" % (case.name, template.code),
                        "case_id": case.id,
                        "template_id": template.id,
                    })
        return True

    def action_approve_internal_review(self):
        self._assert_manager()
        for case in self:
            if case.stage != "s1_review":
                raise UserError(_("Only an S1 case can approve internal review."))
            if not case.reviewer_id or case.reviewer_id == self.env.user:
                raise ValidationError(_("Reviewer and approving manager must be different users."))
            if not case.scope_confirmed or not case.programme_route or not (case.internal_review_summary or "").strip():
                raise ValidationError(_("Confirm scope, programme route and the internal review summary."))
            case._ensure_artifact_codes(["S2-GOVERNANCE"])
            case.with_context(hjig_sseries_workflow=True).write({
                "stage": "s2_assessment",
                "internal_review_approved_by_id": self.env.user.id,
                "internal_review_approved_on": fields.Datetime.now(),
                "next_action": _("Record GO, HOLD or NO-GO governance decision"),
                "exception_state": "clear",
                "blocker_summary": False,
            })
        return True

    def action_approve_governance(self):
        self._assert_manager()
        for case in self:
            if case.stage != "s2_assessment":
                raise UserError(_("Only an S2 case can approve governance."))
            if not case.governance_decision or not case.risk_level or not (case.governance_summary or "").strip():
                raise ValidationError(_("Governance decision, risk level and assessment summary are required."))
            common = {
                "governance_approved_by_id": self.env.user.id,
                "governance_approved_on": fields.Datetime.now(),
            }
            if case.governance_decision == "hold":
                common.update({
                    "next_action": _("Resolve governance HOLD blockers"),
                    "exception_state": "blocked",
                    "blocker_summary": case.governance_summary,
                })
            elif case.governance_decision == "no_go":
                common.update({
                    "stage": "cancelled",
                    "next_action": _("Closed - NO-GO"),
                    "exception_state": "blocked",
                    "blocker_summary": case.governance_summary,
                })
            else:
                proposal_code = "PG-03" if case.form_type == "portfolio_guard" else ROUTE_PROPOSAL_TEMPLATE[case.programme_route]
                codes = [proposal_code]
                if case.sourcebridge_required and case.programme_route != "sourcebridge_only":
                    codes.append("PB-SB-03")
                # PortfolioGuard issues one umbrella commercial proposal.  Project-level
                # SourceBridge supplements remain attached to the relevant child case.
                commercial_case = case._commercial_authority_case()
                commercial_case._ensure_artifact_codes([proposal_code])
                if len(codes) > 1:
                    case._ensure_artifact_codes(codes[1:])
                common.update({
                    "stage": "s3_proposal",
                    "next_action": _("Approve fee and prepare the controlled commercial proposal"),
                    "exception_state": "clear",
                    "blocker_summary": False,
                })
            case.with_context(hjig_sseries_workflow=True).write(common)
        return True

    def action_prepare_quotation(self):
        self._assert_manager()
        product = self.env.ref("new_hongyijig_custom.product_hjig_sseries_fee").product_variant_id
        for case in self:
            case._assert_commercial_authority()
            if case.stage != "s3_proposal":
                raise UserError(_("Quotation preparation is available only at S3."))
            commercial_cases = case._portfolio_cases()
            if commercial_cases.filtered(lambda item: item.stage != "s3_proposal" or item.governance_decision != "go"):
                raise ValidationError(_(
                    "Every active PortfolioGuard child must have a GO decision and reach S3 before the umbrella quotation."
                ))
            invalid_pricing = commercial_cases.filtered(
                lambda item: item.approved_governance_fee <= 0
                or not (0.30 <= item.target_margin <= 0.40)
            )
            if invalid_pricing:
                raise ValidationError(_(
                    "Each project fee must be positive and each target margin must remain between 30% and 40%."
                ))
            if not (case.payment_terms_summary or "").strip():
                raise ValidationError(_("Controlled payment terms are required before quotation preparation."))
            if not case.proposal_number:
                sequence = "hjig.sseries.proposal.pgd" if case.form_type == "portfolio_guard" else ROUTE_PROPOSAL_SEQUENCE[case.programme_route]
                case.with_context(hjig_sseries_workflow=True).write({
                    "proposal_number": self.env["ir.sequence"].next_by_code(sequence),
                })
            portfolio_total = sum(commercial_cases.mapped("approved_governance_fee"))
            umbrella_snapshot = {
                "commercial_authority_case": case.name,
                "proposal_number": case.proposal_number,
                "proposal_version": case.proposal_version,
                "portfolio_submission": case.client_submission_id,
                "project_count": len(commercial_cases),
                "portfolio_total": portfolio_total,
                "costing_rule_version": case.costing_rule_version,
                "projects": [{
                    "case": child.name,
                    "client_project_id": child.client_project_id,
                    "project_name": child.project_name,
                    "programme_route": child.programme_route,
                    "approved_governance_fee": child.approved_governance_fee,
                    "target_margin": child.target_margin,
                    "sourcebridge_required": child.sourcebridge_required,
                } for child in commercial_cases],
                "approved_by": self.env.user.login,
                "approved_on": fields.Datetime.now().isoformat(),
            }
            if not case.sale_order_id:
                order = self.env["sale.order"].sudo().create({
                    "partner_id": case.partner_id.id,
                    "company_id": case.company_id.id,
                    "origin": case.client_submission_id,
                    "client_order_ref": case.proposal_number,
                    "note": case.payment_terms_summary,
                    "hjig_sseries_case_id": case.id,
                })
                for child in commercial_cases:
                    self.env["sale.order.line"].sudo().create({
                        "order_id": order.id,
                        "product_id": product.id,
                        "name": "%s - %s" % (
                            dict(PROGRAMME_ROUTES).get(child.programme_route), child.project_name
                        ),
                        "product_uom_qty": 1.0,
                        "price_unit": child.approved_governance_fee,
                    })
            else:
                order = case.sale_order_id
            approved_on = fields.Datetime.now()
            for child in commercial_cases:
                child_snapshot = dict(
                    umbrella_snapshot,
                    case=child.name,
                    child_case=child.name,
                    programme_route=child.programme_route,
                    approved_governance_fee=child.approved_governance_fee,
                    target_margin=child.target_margin,
                    sourcebridge_required=child.sourcebridge_required,
                )
                child.with_context(hjig_sseries_workflow=True).write({
                    "proposal_number": case.proposal_number,
                    "proposal_version": case.proposal_version,
                    "sale_order_id": order.id,
                    "pricing_snapshot_json": child_snapshot,
                    "commercial_approved_by_id": self.env.user.id,
                    "commercial_approved_on": approved_on,
                    "payment_terms_summary": case.payment_terms_summary,
                    "next_action": (
                        _("Attach and approve the umbrella commercial PDF; then record customer acceptance")
                        if child == case else _("Covered by umbrella proposal %s") % case.proposal_number
                    ),
                })
        return True

    def action_record_customer_acceptance(self):
        self._assert_manager()
        for case in self:
            case._assert_commercial_authority()
            if case.stage != "s3_proposal" or not case.sale_order_id:
                raise UserError(_("A prepared S3 quotation is required."))
            commercial_cases = case._portfolio_cases()
            if commercial_cases.filtered(lambda item: item.stage != "s3_proposal"):
                raise ValidationError(_("All PortfolioGuard children must remain at S3 until umbrella acceptance."))
            proposal_code = "PG-03" if case.form_type == "portfolio_guard" else ROUTE_PROPOSAL_TEMPLATE[case.programme_route]
            proposal = case.artifact_ids.filtered(lambda item: item.code == proposal_code)[:1]
            if not proposal or proposal.state not in ("approved", "issued") or not proposal.customer_issue_allowed:
                raise ValidationError(_("The exact-master commercial proposal requires approval and customer issue permission."))
            if not case.acceptance_basis or not (case.acceptance_reference or "").strip() or not case.acceptance_date:
                raise ValidationError(_("Signed proposal or PO acceptance evidence and date are required."))
            if case.acceptance_basis == "signed_proposal" and not (
                case.customer_signature_received and case.hongyi_countersigned
            ):
                raise ValidationError(_(
                    "A signed-proposal acceptance needs both customer signature and Hongyi countersignature."
                ))
            if case.acceptance_basis == "purchase_order" and not case.purchase_order_received:
                raise ValidationError(_("Purchase Order receipt evidence is required for PO acceptance."))
            if commercial_cases.filtered(lambda item: item.nda_required and not item.nda_completed):
                raise ValidationError(_("The required NDA must be completed before activation."))
            case._ensure_artifact_codes([
                "S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S5-PROFORMA",
                "S5-PAYMENT-EVIDENCE",
            ] + (["S4-NDA"] if case.nda_required else []))
            for child in commercial_cases:
                child.with_context(hjig_sseries_workflow=True).write({
                    "stage": "s4_activation",
                    "acceptance_basis": case.acceptance_basis,
                    "acceptance_reference": case.acceptance_reference,
                    "acceptance_date": case.acceptance_date,
                    "customer_signature_received": case.customer_signature_received,
                    "hongyi_countersigned": case.hongyi_countersigned,
                    "purchase_order_received": case.purchase_order_received,
                    "next_action": (
                        _("Complete umbrella Order Punch, Finance and payment evidence")
                        if child == case else _("Umbrella acceptance recorded; activation is controlled by %s") % case.name
                    ),
                })
        return True

    def action_complete_activation(self):
        self._assert_manager()
        for case in self:
            case._assert_commercial_authority()
            if case.stage != "s4_activation":
                raise UserError(_("Activation can be completed only at S4."))
            commercial_cases = case._portfolio_cases()
            if commercial_cases.filtered(lambda item: item.stage != "s4_activation"):
                raise ValidationError(_("All PortfolioGuard children must be at S4 before umbrella activation."))
            if not case.order_number:
                case.with_context(hjig_sseries_workflow=True).write({
                    "order_number": self.env["ir.sequence"].next_by_code("hjig.sseries.order"),
                })
            if not (case.proforma_reference or "").strip() or not case.finance_approved:
                raise ValidationError(_("Finance-approved Proforma Invoice evidence is required."))
            if not case.payment_received or not (case.payment_evidence_reference or "").strip():
                raise ValidationError(_("Payment receipt and bank-evidence reference are required."))
            order_punch = case.artifact_ids.filtered(lambda item: item.code == "S5-ORDER-PUNCH")[:1]
            if not order_punch or order_punch.state != "approved":
                raise ValidationError(_("Approved Order Punch document is required."))
            order = case.sale_order_id.sudo()
            if order.state not in ("sale", "done"):
                order.action_confirm()
            for child in commercial_cases:
                child._ensure_artifact_codes(["S6-TEAM-HANDOVER"])
                next_stage = "s5_sourcing" if child.sourcebridge_required else "s6_handover"
                if child.sourcebridge_required:
                    child._ensure_artifact_codes([
                        "S6-CHINA-HANDOVER", "S6-SUPPLIER-RFQ-EN", "S6-SUPPLIER-RFQ-ZH",
                    ])
                child.with_context(hjig_sseries_workflow=True).write({
                    "stage": next_stage,
                    "order_number": case.order_number,
                    "order_punch_approved": True,
                    "proforma_reference": case.proforma_reference,
                    "finance_approved": case.finance_approved,
                    "payment_received": case.payment_received,
                    "payment_evidence_reference": case.payment_evidence_reference,
                    "next_action": _("Approve the conditional sourcing pack") if child.sourcebridge_required
                                   else _("Complete team handover and release B0"),
                })
        return True

    def action_complete_sourcing_pack(self):
        self._assert_manager()
        required = {"S6-CHINA-HANDOVER", "S6-SUPPLIER-RFQ-EN", "S6-SUPPLIER-RFQ-ZH"}
        for case in self:
            if case.stage != "s5_sourcing" or not case.sourcebridge_required:
                raise UserError(_("A conditional SourceBridge sourcing case is required."))
            approved = set(case.artifact_ids.filtered(lambda item: item.state == "approved").mapped("code"))
            missing = required - approved
            if missing:
                raise ValidationError(_("Approve the full internal sourcing pack first: %s") % ", ".join(sorted(missing)))
            case.with_context(hjig_sseries_workflow=True).write({
                "stage": "s6_handover",
                "next_action": _("Complete team handover and release B0"),
            })
        return True

    def _ensure_portfolio_guard(self):
        self.ensure_one()
        if self.form_type != "portfolio_guard":
            return self.env["hjig.portfolio.guard"]
        authority = self._commercial_authority_case()
        order = authority.sale_order_id.sudo()
        portfolio = authority.portfolio_guard_id or self.env["hjig.portfolio.guard"].sudo().search([
            ("sale_order_id", "=", order.id),
        ], limit=1)
        if not portfolio:
            portfolio = self.env["hjig.portfolio.guard"].sudo().create({
                "name": "%s / %s" % (authority.proposal_number, authority.customer_name),
                "partner_id": authority.partner_id.id,
                "sale_order_id": order.id,
                "owner_designation_id": self.env.ref(
                    "new_hongyijig_custom.designation_project_manager"
                ).id,
                "approver_designation_id": self.env.ref(
                    "new_hongyijig_custom.designation_pmo_document_controller"
                ).id,
            })
        for child in authority._portfolio_cases():
            if child.portfolio_guard_id != portfolio:
                child.with_context(hjig_sseries_workflow=True).write({
                    "portfolio_guard_id": portfolio.id,
                })
        return portfolio

    def _activate_portfolio_bseries_programme_run(self):
        """Activate one child project/run under the shared PortfolioGuard commercial order."""
        self.ensure_one()
        portfolio = self._ensure_portfolio_guard()
        if self.programme_run_id:
            if self.programme_run_id.portfolio_guard_id != portfolio:
                raise ValidationError(_("The existing programme run is outside the PortfolioGuard umbrella."))
            return self.programme_run_id
        template_code = ROUTE_PROGRAMME_TEMPLATE.get(self.programme_route)
        sequence_code = ROUTE_PROJECT_SEQUENCE.get(self.programme_route)
        if not template_code or not sequence_code:
            raise ValidationError(_("The selected child route has no controlled B-Series mapping."))
        version = self.env["hjig.programme.template.version"].search([
            ("template_id.code", "=", template_code),
            ("state", "=", "approved"),
            ("is_current", "=", True),
        ], limit=1)
        if not version:
            raise ValidationError(_(
                "No current approved %s programme version exists. Approve the B-Series master before B0 release."
            ) % template_code)
        project_code = self.env["ir.sequence"].next_by_code(sequence_code)
        if not project_code:
            raise ValidationError(_("The governed project-code sequence is unavailable."))
        authorised_users = (self.env.user | self.handover_owner_id).ids
        project = self.env["project.project"].sudo().with_context(
            hjig_sseries_activation=True
        ).create({
            "name": self.project_name,
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "hjig_project_record_type": "customer",
            "hjig_programme": self.programme_route,
            "hjig_authorized_user_ids": [(6, 0, authorised_users)],
            "x_project_code": project_code,
        })
        run = self.env["hjig.programme.run"].sudo().create({
            "name": "%s / %s" % (project_code, version.name),
            "sale_order_id": self.sale_order_id.id,
            "project_id": project.id,
            "template_version_id": version.id,
            "portfolio_guard_id": portfolio.id,
        })
        run._ensure_scope_decisions()
        self.with_context(hjig_sseries_workflow=True).write({
            "project_id": project.id,
            "programme_run_id": run.id,
        })
        return run

    def _activate_bseries_programme_run(self):
        """Create the governed B-Series execution records immediately before B0 release."""
        self.ensure_one()
        template_code = ROUTE_PROGRAMME_TEMPLATE.get(self.programme_route)
        sequence_code = ROUTE_PROJECT_SEQUENCE.get(self.programme_route)
        if not template_code or not sequence_code:
            raise ValidationError(_("The selected programme route has no controlled B-Series mapping."))
        version = self.env["hjig.programme.template.version"].search([
            ("template_id.code", "=", template_code),
            ("state", "=", "approved"),
            ("is_current", "=", True),
        ], limit=1)
        if not version:
            raise ValidationError(_(
                "No current approved %s programme version exists. Approve the B-Series master before B0 release."
            ) % template_code)
        order = self.sale_order_id.sudo()
        run = order.hjig_programme_run_id
        if run:
            if run.template_version_id != version:
                raise ValidationError(_("The existing programme run does not match the current approved route."))
        else:
            project_code = self.env["ir.sequence"].next_by_code(sequence_code)
            if not project_code:
                raise ValidationError(_("The governed project-code sequence is unavailable."))
            order.with_context(hjig_programme_activation=True).write({
                "hjig_programme_version_id": version.id,
                "hjig_project_code": project_code,
            })
            order.with_context(hjig_sseries_activation=True).action_activate_hjig_programme()
            order.invalidate_recordset(["hjig_project_id", "hjig_programme_run_id"])
            run = order.hjig_programme_run_id
        if not run or not order.hjig_project_id:
            raise ValidationError(_("B-Series project and programme run creation did not complete."))
        self.with_context(hjig_sseries_workflow=True).write({
            "project_id": order.hjig_project_id.id,
            "programme_run_id": run.id,
        })
        return run

    @api.model
    def _sourcebridge_component_category(self, component_type):
        text = (component_type or "").strip().lower()
        if "tool" in text or "mould" in text or "mold" in text:
            return "tooling"
        if "plastic" in text:
            return "plastic"
        if "metal" in text:
            return "metal"
        if "material" in text:
            return "material"
        if "service" in text or "process" in text:
            return "service"
        if "bought" in text or "purchase" in text or "component" in text:
            return "bought_out"
        return "other"

    def _activate_sourcebridge_handover(self):
        """Create a standalone SourceBridge project without pretending it is a B-Series run."""
        self.ensure_one()
        components = self.intake_project_id.component_ids
        if not components:
            raise ValidationError(_("SourceBridge B0 release requires at least one governed intake component."))
        if self.sourcebridge_engagement_id:
            return self.sourcebridge_engagement_id
        project_code = self.env["ir.sequence"].next_by_code("hjig.sseries.project.sbg")
        engagement_code = self.env["ir.sequence"].next_by_code("hjig.sseries.sourcebridge.engagement")
        if not project_code or not engagement_code:
            raise ValidationError(_("SourceBridge project or engagement sequence is unavailable."))
        authorised_users = (self.env.user | self.handover_owner_id).ids
        project = self.env["project.project"].sudo().with_context(
            hjig_sseries_activation=True
        ).create({
            "name": "%s - SourceBridge" % self.project_name,
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "hjig_project_record_type": "customer",
            "hjig_programme": "sourcebridge_only",
            "hjig_authorized_user_ids": [(6, 0, authorised_users)],
            "x_project_code": project_code,
        })
        Engagement = self.env["hjig.sourcebridge.engagement"].sudo()
        engagement = Engagement.create({
            "code": engagement_code,
            "name": "%s / %s" % (project_code, self.project_name),
            "project_id": project.id,
            "sseries_case_id": self.id,
            "sale_order_id": self.sale_order_id.id,
            "owner_designation_id": self.env.ref(
                "new_hongyijig_custom.designation_project_manager"
            ).id,
            "approver_designation_id": self.env.ref(
                "new_hongyijig_custom.designation_pmo_document_controller"
            ).id,
        })
        Component = self.env["hjig.sourcebridge.component"].sudo()
        for component in components:
            specification_parts = [
                component.component_function,
                component.preferred_solution_route,
                component.material_grade,
                component.technical_specification_status,
            ]
            Component.create({
                "engagement_id": engagement.id,
                "sequence": component.sequence,
                "code": "%s-C%02d" % (engagement_code, component.component_index),
                "name": component.name,
                "category": self._sourcebridge_component_category(component.component_type),
                "quantity": component.expected_year_1_quantity or 1,
                "specification": " | ".join(item.strip() for item in specification_parts if item and item.strip()),
            })
        self.with_context(hjig_sseries_workflow=True).write({
            "project_id": project.id,
            "sourcebridge_engagement_id": engagement.id,
        })
        return engagement

    def _activate_execution_handover(self):
        self.ensure_one()
        if self.form_type == "portfolio_guard":
            self._ensure_portfolio_guard()
            if self.programme_route != "sourcebridge_only":
                return self._activate_portfolio_bseries_programme_run()
        if self.programme_route == "sourcebridge_only":
            return self._activate_sourcebridge_handover()
        return self._activate_bseries_programme_run()

    def action_release_b0(self):
        self._assert_manager()
        for case in self:
            if case.stage != "s6_handover":
                raise UserError(_("B0 release is available only after S6 handover."))
            handover = case.artifact_ids.filtered(lambda item: item.code == "S6-TEAM-HANDOVER")[:1]
            if not handover or handover.state != "approved" or not case.handover_owner_id or not case.handover_accepted:
                raise ValidationError(_("Approved Team Handover, responsible owner and acceptance are required."))
            if not case.order_punch_approved or not case.payment_received or not case.sale_order_id:
                raise ValidationError(_("Commercial acceptance, Order Punch and payment gates are incomplete."))
            case._activate_execution_handover()
            manifest = self.env["hjig.sseries.b0.handover"].with_context(
                hjig_sseries_workflow=True
            ).create_from_case(case)
            case.with_context(hjig_sseries_workflow=True).write({
                "stage": "b0_released",
                "b0_manifest_id": manifest.id,
                "next_action": _("B0 handover released - execution team owns the next action"),
                "exception_state": "clear",
                "blocker_summary": False,
            })
        return True


class HjigSSeriesB0Handover(models.Model):
    _name = "hjig.sseries.b0.handover"
    _description = "Immutable S-Series to B0 Handover Manifest"
    _order = "released_on desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    case_id = fields.Many2one("hjig.sseries.case", required=True, readonly=True, ondelete="restrict", index=True)
    programme_route = fields.Selection(PROGRAMME_ROUTES, required=True, readonly=True)
    partner_id = fields.Many2one("res.partner", required=True, readonly=True, ondelete="restrict")
    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True, ondelete="restrict")
    project_id = fields.Many2one("project.project", readonly=True, ondelete="restrict")
    programme_run_id = fields.Many2one("hjig.programme.run", readonly=True, ondelete="restrict")
    sourcebridge_engagement_id = fields.Many2one(
        "hjig.sourcebridge.engagement", readonly=True, ondelete="restrict"
    )
    portfolio_guard_id = fields.Many2one(
        "hjig.portfolio.guard", readonly=True, ondelete="restrict"
    )
    sourcebridge_required = fields.Boolean(readonly=True)
    snapshot_json = fields.Json(required=True, readonly=True, copy=False)
    snapshot_sha256 = fields.Char(required=True, readonly=True, copy=False, index=True)
    released_by_id = fields.Many2one("res.users", required=True, readonly=True, copy=False)
    released_on = fields.Datetime(required=True, readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, readonly=True)

    _case_unique = models.Constraint("UNIQUE(case_id)", "An S-Series case can have only one B0 manifest.")

    @api.model
    def create_from_case(self, case):
        if not self.env.context.get("hjig_sseries_workflow"):
            raise UserError(_("B0 manifests are created only by the governed S-Series release action."))
        released_by_id = self.env.user.id
        snapshot = {
            "case": case.name,
            "submission": case.client_submission_id,
            "project": case.client_project_id,
            "programme_route": case.programme_route,
            "proposal_number": case.proposal_number,
            "proposal_version": case.proposal_version,
            "order_number": case.order_number,
            "sale_order": case.sale_order_id.sudo().name,
            "project_code": case.project_id.x_project_code,
            "programme_run": case.programme_run_id.name,
            "sourcebridge_engagement": case.sourcebridge_engagement_id.code,
            "portfolio_guard": case.portfolio_guard_id.name,
            "payment_evidence_reference": case.payment_evidence_reference,
            "tax_invoice_reference": case.tax_invoice_reference,
            "sourcebridge_required": case.sourcebridge_required,
            "handover_owner": case.handover_owner_id.login,
            "released_on": fields.Datetime.now().isoformat(),
        }
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.sudo().create({
            "name": self.env["ir.sequence"].next_by_code("hjig.sseries.b0.handover"),
            "case_id": case.id,
            "programme_route": case.programme_route,
            "partner_id": case.partner_id.id,
            "sale_order_id": case.sale_order_id.id,
            "project_id": case.project_id.id,
            "programme_run_id": case.programme_run_id.id,
            "sourcebridge_engagement_id": case.sourcebridge_engagement_id.id,
            "portfolio_guard_id": case.portfolio_guard_id.id,
            "sourcebridge_required": case.sourcebridge_required,
            "snapshot_json": snapshot,
            "snapshot_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "released_by_id": released_by_id,
            "released_on": fields.Datetime.now(),
            "company_id": case.company_id.id,
        })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hjig_sseries_workflow"):
            raise UserError(_("B0 manifests are created only by governed workflow actions."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("A released B0 handover manifest is immutable."))

    def unlink(self):
        raise UserError(_("A released B0 handover manifest cannot be deleted."))
