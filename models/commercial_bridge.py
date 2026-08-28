# -*- coding: utf-8 -*-

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from .workflow_guard import is_workflow_context, workflow_context


COMMERCIAL_DOCUMENT_MODELS = [
    ("sale.order", "Customer Sales Order"),
    ("purchase.order", "Supplier Purchase Order"),
    ("account.move", "Invoice / Bill / Credit Note"),
    ("account.payment", "Customer / Supplier Payment"),
]


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [("hjig.commercial.link", "Project Commercial Link")]


class HjigCommercialSubmission(models.Model):
    _name = "hjig.commercial.submission"
    _description = "Hongyi Immutable Commercial Submission Snapshot"
    _order = "link_id, revision desc"

    link_id = fields.Many2one("hjig.commercial.link", required=True, ondelete="restrict", index=True)
    project_id = fields.Many2one("project.project", required=True, readonly=True, ondelete="restrict", index=True)
    company_id = fields.Many2one("res.company", readonly=True, ondelete="restrict", index=True)
    revision = fields.Integer(required=True, readonly=True)
    snapshot_hash = fields.Char(required=True, readonly=True, index=True)
    snapshot = fields.Text(required=True, readonly=True)
    approval_id = fields.Many2one("hjig.approval", required=True, ondelete="restrict", readonly=True)
    submitted_by_id = fields.Many2one("res.users", required=True, readonly=True)
    submitted_date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)

    _link_revision_unique = models.Constraint(
        "UNIQUE(link_id, revision)", "Commercial submission revision must be unique for the link."
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not is_workflow_context(self.env):
            raise UserError(_("Commercial submission snapshots are created only by the controlled review workflow."))
        for vals in vals_list:
            link = self.env["hjig.commercial.link"].browse(vals.get("link_id")).exists()
            approval = self.env["hjig.approval"].browse(vals.get("approval_id")).exists()
            if not link or not approval:
                raise ValidationError(_("A commercial submission requires its controlled link and approval request."))
            if vals.get("project_id") != link.project_id.id or vals.get("company_id") != link.company_id.id:
                raise ValidationError(_("Submission project and company must match the commercial link at submission time."))
            if approval.project_id != link.project_id or approval.approval_type != "commercial":
                raise ValidationError(_("The submission approval must be a commercial approval for the same project."))
            if approval.target_ref != link:
                raise ValidationError(_("The submission approval must target this commercial link."))
            if vals.get("snapshot_hash") != approval.request_snapshot_hash:
                raise ValidationError(_("The immutable submission hash must match the approval request hash."))
            if vals.get("revision") != link.revision + 1:
                raise ValidationError(_("The submission revision must be the next commercial-link revision."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Commercial submission snapshots are immutable."))

    def unlink(self):
        raise UserError(_("Commercial submission snapshots cannot be deleted."))


class HjigCommercialLink(models.Model):
    """Project view over authoritative commercial documents, not a second ledger."""

    _name = "hjig.commercial.link"
    _description = "Hongyi Project Commercial Link"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, transaction_date desc, code desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    ledger_side = fields.Selection(
        [("customer", "Customer"), ("supplier", "Supplier")], required=True, index=True, tracking=True
    )
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", index=True, tracking=True)
    entry_kind = fields.Selection(
        [
            ("order", "Order / Contract"),
            ("invoice", "Invoice / Supplier Bill"),
            ("payment", "Receipt / Payment"),
            ("credit_note", "Credit / Debit Adjustment"),
            ("ecn_adjustment", "ECN Commercial Impact"),
            ("other", "Other Commercial Record"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    transaction_ref = fields.Reference(
        selection="_selection_commercial_document_model",
        string="Authoritative Odoo Document",
        tracking=True,
        help="Link the existing order, invoice, bill, credit note, or payment. Values are read from that record.",
    )
    external_reference = fields.Char(
        tracking=True,
        help="Use only when the authoritative commercial document is outside this Odoo database.",
    )
    ecn_ref = fields.Reference(
        selection="_selection_ecn_model",
        string="Related ECN",
        tracking=True,
        help="Optional link to the existing ECN register. ECN commercial-impact entries require this link.",
    )
    transaction_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id.id, ondelete="restrict"
    )
    external_amount = fields.Monetary(
        currency_field="currency_id",
        tracking=True,
        help="Use only for an external document. Odoo document amounts are read automatically.",
    )
    authoritative_amount = fields.Monetary(
        currency_field="currency_id", compute="_compute_document_snapshot", string="Ledger Amount"
    )
    document_state = fields.Char(compute="_compute_document_snapshot")
    payment_state = fields.Char(compute="_compute_document_snapshot")
    approved_amount = fields.Monetary(currency_field="currency_id", readonly=True, copy=False)
    revision = fields.Integer(default=0, readonly=True, copy=False)
    verified_snapshot_hash = fields.Char(readonly=True, copy=False, index=True)
    source_drift = fields.Boolean(compute="_compute_document_snapshot", string="Source Changed After Verification")
    reference_health = fields.Selection(
        [
            ("valid", "Valid"), ("changed", "Changed"), ("missing", "Missing"),
            ("orphaned", "Orphaned Model/Record"), ("inaccessible", "Native Document Access Required"),
        ],
        compute="_compute_document_snapshot",
    )
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    approval_authority_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approval_id = fields.Many2one("hjig.approval", readonly=True, copy=False, ondelete="restrict")
    current_submission_id = fields.Many2one(
        "hjig.commercial.submission", readonly=True, copy=False, ondelete="restrict"
    )
    submission_ids = fields.One2many("hjig.commercial.submission", "link_id", string="Submission History")
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("verified", "Verified"), ("rejected", "Rejected")],
        default="draft", required=True, copy=False, index=True, tracking=True,
    )
    notes = fields.Text(tracking=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Commercial link code must be unique.")

    @api.model
    def _selection_commercial_document_model(self):
        return [(model, label) for model, label in COMMERCIAL_DOCUMENT_MODELS if model in self.env.registry]

    @api.model
    def _selection_ecn_model(self):
        return (
            [("hjig.project.ecn", "Engineering Change Notice")]
            if "hjig.project.ecn" in self.env.registry else []
        )

    def _safe_reference(self, field_name):
        """Return (record, orphaned) without letting a removed model/record break the UI."""
        self.ensure_one()
        try:
            record = self[field_name]
            if record and not record.exists():
                return False, True
            return record, False
        except (KeyError, MissingError):
            return False, True

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.commercial.link") or _("New")
        return super().create(vals_list)

    def _document_profile(self):
        self.ensure_one()
        document, orphaned = self._safe_reference("transaction_ref")
        if not document:
            model = "external" if self.external_reference else "orphaned" if orphaned or self.revision else "missing"
            return {
                "model": model, "record": (self.external_reference or "").strip(),
                "state": model, "payment_state": False, "subtype": False,
                "partner_type": self.ledger_side, "amount": self.external_amount or 0.0,
                "currency_id": self.currency_id.id, "date": fields.Date.to_string(self.transaction_date),
            }
        try:
            document.check_access("read")
            amount = 0.0
            for field_name in ("amount_total", "amount", "amount_total_signed"):
                if field_name in document._fields:
                    amount = document[field_name] or 0.0
                    break
            source_date = False
            for field_name in ("invoice_date", "date_order", "date"):
                if field_name in document._fields and document[field_name]:
                    source_date = fields.Date.to_date(document[field_name])
                    break
            return {
                "model": document._name,
                "record": "%s,%s" % (document._name, document.id),
                "state": document["state"] if "state" in document._fields else False,
                "payment_state": document["payment_state"] if "payment_state" in document._fields else False,
                "subtype": document["move_type"] if "move_type" in document._fields else False,
                "partner_type": document["partner_type"] if "partner_type" in document._fields else False,
                "amount": amount,
                "currency_id": document.currency_id.id if "currency_id" in document._fields else self.currency_id.id,
                "date": fields.Date.to_string(source_date) if source_date else False,
            }
        except AccessError:
            return {
                "model": "inaccessible", "record": "%s,%s" % (document._name, document.id),
                "state": _("Access denied"), "payment_state": False, "subtype": False,
                "partner_type": False, "amount": 0.0,
                "currency_id": self.currency_id.id, "date": False,
            }
        except MissingError:
            return {
                "model": "orphaned", "record": "%s,%s" % (document._name, document.id),
                "state": "orphaned", "payment_state": False, "subtype": False,
                "partner_type": False, "amount": 0.0,
                "currency_id": self.currency_id.id, "date": False,
            }

    @api.model
    def _validate_source_profile(self, profile, ledger_side, entry_kind, require_final=True):
        model = profile["model"]
        if model == "external":
            return
        if model == "inaccessible":
            raise UserError(_(
                "You need read access to the linked native Odoo commercial document before this entry can be reviewed. Ask an administrator to assign the appropriate Sales, Purchase, Invoicing, or Accounting role."
            ))
        if model == "sale.order":
            if ledger_side != "customer" or entry_kind not in ("order", "ecn_adjustment"):
                raise ValidationError(_("Sales Orders may only support Customer Order or Customer ECN entries."))
            allowed_states = ("sale", "done")
        elif model == "purchase.order":
            if ledger_side != "supplier" or entry_kind not in ("order", "ecn_adjustment"):
                raise ValidationError(_("Purchase Orders may only support Supplier Order or Supplier ECN entries."))
            allowed_states = ("purchase", "done")
        elif model == "account.move":
            subtype_map = {
                "out_invoice": ("customer", ("invoice", "ecn_adjustment")),
                "out_refund": ("customer", ("credit_note", "ecn_adjustment")),
                "in_invoice": ("supplier", ("invoice", "ecn_adjustment")),
                "in_refund": ("supplier", ("credit_note", "ecn_adjustment")),
            }
            expected = subtype_map.get(profile["subtype"])
            if not expected or ledger_side != expected[0] or entry_kind not in expected[1]:
                raise ValidationError(_("Invoice/Bill type does not match the selected ledger side and entry kind."))
            allowed_states = ("posted",)
        elif model == "account.payment":
            if entry_kind != "payment" or profile["partner_type"] != ledger_side:
                raise ValidationError(_("Payment partner type must match the Customer or Supplier ledger side."))
            allowed_states = ("in_process", "paid", "posted")
        else:
            raise ValidationError(_("Unsupported authoritative commercial document model."))
        if require_final and profile["state"] not in allowed_states:
            raise ValidationError(_("The authoritative commercial document is still Draft, Cancelled, or otherwise unapproved."))

    def _snapshot_text_and_hash(self, next_revision=None):
        self.ensure_one()
        profile = self._document_profile()
        ecn, ecn_orphaned = self._safe_reference("ecn_ref")
        payload = {
            "revision": next_revision if next_revision is not None else self.revision,
            "project_id": self.project_id.id, "ledger_side": self.ledger_side,
            "partner_id": self.partner_id.commercial_partner_id.id, "entry_kind": self.entry_kind,
            "transaction": profile,
            "ecn": "%s,%s" % (ecn._name, ecn.id) if ecn else "orphaned" if ecn_orphaned else False,
            "transaction_date": fields.Date.to_string(self.transaction_date),
            "currency_id": self.currency_id.id, "notes": self.notes or "",
        }
        snapshot = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return snapshot, hashlib.sha256(snapshot.encode("utf-8")).hexdigest()

    @api.depends(
        "transaction_ref", "external_reference", "external_amount", "currency_id",
        "ecn_ref", "transaction_date", "verified_snapshot_hash", "revision", "notes",
    )
    def _compute_document_snapshot(self):
        for link in self:
            profile = link._document_profile()
            _ecn, ecn_orphaned = link._safe_reference("ecn_ref")
            link.authoritative_amount = profile["amount"]
            link.document_state = profile["state"] or _("Linked")
            link.payment_state = profile["payment_state"] or False
            if link.verified_snapshot_hash:
                _snapshot, current_hash = link._snapshot_text_and_hash()
                link.source_drift = current_hash != link.verified_snapshot_hash
            else:
                link.source_drift = False
            if profile["model"] == "orphaned" or ecn_orphaned:
                link.reference_health = "orphaned"
            elif profile["model"] == "inaccessible":
                link.reference_health = "inaccessible"
            elif profile["model"] == "missing":
                link.reference_health = "missing"
            elif link.source_drift:
                link.reference_health = "changed"
            else:
                link.reference_health = "valid"

    @api.constrains(
        "project_id", "company_id", "ledger_side", "partner_id", "entry_kind", "transaction_ref",
        "external_reference", "ecn_ref", "currency_id", "external_amount",
    )
    def _check_commercial_integrity(self):
        for link in self:
            document, document_orphaned = link._safe_reference("transaction_ref")
            ecn, ecn_orphaned = link._safe_reference("ecn_ref")
            if document_orphaned:
                raise ValidationError(_("The authoritative Odoo commercial document no longer exists or its module is unavailable."))
            if ecn_orphaned:
                raise ValidationError(_("The linked ECN no longer exists or its module is unavailable."))
            if ecn:
                try:
                    ecn.check_access("read")
                except AccessError as error:
                    raise UserError(_("You need read access to the linked ECN before this entry can be reviewed.")) from error
            if not document and not (link.external_reference or "").strip():
                raise ValidationError(_("Link an authoritative Odoo document or enter its external reference."))
            if document and (link.external_reference or "").strip():
                raise ValidationError(_("Use either the Odoo document link or the external reference, not both."))
            if document and link.external_amount:
                raise ValidationError(_("External Amount must be zero when an authoritative Odoo document is linked."))
            if link.external_amount < 0:
                raise ValidationError(_("Commercial amounts must be entered as positive values; ledger side determines direction."))
            if link.entry_kind == "ecn_adjustment" and not ecn:
                raise ValidationError(_("An ECN Commercial Impact entry must link the existing ECN record."))
            if ecn and ecn.project_id != link.project_id:
                raise ValidationError(_("The ECN and commercial entry must belong to the same project."))
            if document:
                try:
                    document.check_access("read")
                except AccessError as error:
                    raise UserError(_(
                        "You need read access to the linked native Odoo commercial document. Ask an administrator to assign the appropriate Sales, Purchase, Invoicing, or Accounting role."
                    )) from error
                document_company = document.company_id if "company_id" in document._fields else False
                if document_company and document_company != link.company_id:
                    raise ValidationError(_("The commercial document must belong to the same company."))
                document_partner = document.partner_id if "partner_id" in document._fields else False
                if document_partner and document_partner.commercial_partner_id != link.partner_id.commercial_partner_id:
                    raise ValidationError(_("The commercial document partner must match the ledger partner."))
                document_currency = document.currency_id if "currency_id" in document._fields else False
                if document_currency and document_currency != link.currency_id:
                    raise ValidationError(_("The selected currency must match the authoritative commercial document."))
                link._validate_source_profile(link._document_profile(), link.ledger_side, link.entry_kind, require_final=False)

    def _check_source_ready_for_verification(self):
        for link in self:
            link._check_commercial_integrity()
            profile = link._document_profile()
            link._validate_source_profile(profile, link.ledger_side, link.entry_kind, require_final=True)
            if profile["amount"] <= 0:
                raise ValidationError(_("A commercial link requires a positive authoritative amount."))
            if profile["date"] and fields.Date.to_date(profile["date"]) != link.transaction_date:
                raise ValidationError(_("Transaction Date must match the authoritative commercial document date."))

    def write(self, vals):
        workflow = {
            "state", "approval_id", "current_submission_id", "revision",
            "approved_amount", "verified_snapshot_hash",
        }
        if workflow.intersection(vals) and not is_workflow_context(self.env):
            raise ValidationError(_("Commercial verification fields may only change through workflow actions."))
        governed = {
            "project_id", "ledger_side", "partner_id", "entry_kind", "transaction_ref", "external_reference",
            "ecn_ref", "transaction_date", "currency_id", "external_amount", "owner_id", "notes",
            "approval_authority_designation_id",
        }
        if governed.intersection(vals) and any(link.state in ("review", "verified") for link in self):
            raise ValidationError(_("A submitted or verified commercial link is read-only."))
        return super().write(vals)

    def unlink(self):
        if any(link.state != "draft" for link in self):
            raise UserError(_("Only Draft commercial links may be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for link in self:
            if link.state not in ("draft", "rejected"):
                raise UserError(_("Only Draft or Rejected commercial links can be submitted."))
            if link.owner_id != self.env.user and not self.env.user.has_group("project.group_project_manager"):
                raise UserError(_("Only the Commercial Link Owner or a Project Manager may submit this record."))
            link._check_source_ready_for_verification()
            previous_state = link.state
            next_revision = link.revision + 1
            snapshot, snapshot_hash = link._snapshot_text_and_hash(next_revision=next_revision)
            approval = self.env["hjig.approval"].sudo().create({
                "project_id": link.project_id.id,
                "target_ref": "%s,%s" % (link._name, link.id),
                "approval_type": "commercial",
                "authority_designation_id": link.approval_authority_designation_id.id,
                "requested_by_id": self.env.user.id,
                "request_snapshot_hash": snapshot_hash,
            })
            submission = self.env["hjig.commercial.submission"].sudo().with_context(**workflow_context()).create({
                "link_id": link.id, "project_id": link.project_id.id, "company_id": link.company_id.id,
                "revision": next_revision,
                "snapshot": snapshot, "snapshot_hash": snapshot_hash,
                "approval_id": approval.id, "submitted_by_id": self.env.user.id,
            })
            link.with_context(**workflow_context()).write({
                "state": "review", "approval_id": approval.id,
                "current_submission_id": submission.id, "revision": next_revision,
            })
            link._log_transition(previous_state, "review", "submitted", approval)

    def action_apply_decision(self):
        for link in self:
            if link.state != "review" or not link.approval_id:
                raise UserError(_("The commercial link has no approval decision to apply."))
            if link.approval_id.state == "approved":
                link._check_source_ready_for_verification()
                next_state = "verified"
            elif link.approval_id.state == "rejected":
                next_state = "rejected"
            else:
                raise UserError(_("The commercial approval decision is still pending."))
            values = {"state": next_state}
            if next_state == "verified":
                _snapshot, current_hash = link._snapshot_text_and_hash()
                if current_hash != link.approval_id.request_snapshot_hash:
                    raise ValidationError(_("The commercial source or mapping changed after submission. Resubmit for approval."))
                values.update({
                    "approved_amount": link.authoritative_amount,
                    "verified_snapshot_hash": current_hash,
                })
            link.with_context(**workflow_context()).write(values)
            link._log_transition("review", next_state, link.approval_id.state, link.approval_id)

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
