# -*- coding: utf-8 -*-

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .workflow_guard import (
    record_staging_demo_transition,
    staging_self_approval_demo_enabled,
)


CHATTER_FIELDS = {"message_follower_ids", "message_ids", "activity_ids"}


class HjigBop(models.Model):
    _name = "hjig.bop"
    _description = "Bought Out Parts Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "code"
    _order = "project_id, revision desc, id desc"

    code = fields.Char(
        required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True
    )
    project_id = fields.Many2one(
        "project.project", required=True, ondelete="restrict", index=True, tracking=True
    )
    project_code = fields.Char(related="project_id.x_project_code", store=True, readonly=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    title = fields.Char(required=True, default="Bought Out Parts Register", tracking=True)
    revision = fields.Char(required=True, default="R00", tracking=True)
    line_ids = fields.One2many("hjig.bop.line", "bop_id", string="Bought Out Parts")
    line_count = fields.Integer(compute="_compute_readiness")
    ready_line_count = fields.Integer(compute="_compute_readiness")
    completion_percent = fields.Float(compute="_compute_readiness")
    all_physical_samples_received = fields.Boolean(compute="_compute_readiness")
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict", tracking=True
    )
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    frozen_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    effective_date = fields.Date(tracking=True)
    customer_signoff_name = fields.Char(tracking=True)
    customer_signoff_designation = fields.Char(tracking=True)
    customer_signoff_date = fields.Date(tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("frozen", "Frozen"),
            ("rejected", "Rejected"),
            ("superseded", "Superseded"),
        ],
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    snapshot_hash = fields.Char(readonly=True, copy=False, tracking=True)
    notes = fields.Text()

    _project_revision_unique = models.Constraint(
        "UNIQUE(project_id, revision)",
        "This BOP revision already exists for the project.",
    )

    @api.depends(
        "line_ids",
        "line_ids.quantity",
        "line_ids.datasheet_status",
        "line_ids.cad_status",
        "line_ids.size_status",
        "line_ids.sample_status",
    )
    def _compute_readiness(self):
        for bop in self:
            bop.line_count = len(bop.line_ids)
            ready = bop.line_ids.filtered("is_ready")
            bop.ready_line_count = len(ready)
            bop.completion_percent = (
                100.0 * len(ready) / len(bop.line_ids) if bop.line_ids else 0.0
            )
            bop.all_physical_samples_received = bool(bop.line_ids) and all(
                line.sample_status == "received" for line in bop.line_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        artifact = self.env.ref(
            "new_hongyijig_custom.artifact_frm_004", raise_if_not_found=False
        )
        sequence = self.env["ir.sequence"]
        records = self.browse()
        for vals in vals_list:
            vals["state"] = "draft"
            if artifact:
                vals.setdefault("owner_designation_id", artifact.owner_designation_id.id)
                vals.setdefault("approver_designation_id", artifact.approver_designation_id.id)
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.bop") or _("New")
        records = super().create(vals_list)
        requirement_id = self.env.context.get("hjig_programme_artifact_requirement_id")
        if requirement_id and len(records) == 1:
            requirement = self.env["hjig.programme.run.artifact"].browse(requirement_id).exists()
            if requirement and requirement.artifact_code == "FRM-004":
                requirement.bop_id = records.id
        return records

    def _snapshot_payload(self):
        self.ensure_one()
        return {
            "project_id": self.project_id.id,
            "revision": self.revision,
            "effective_date": fields.Date.to_string(self.effective_date),
            "lines": [
                {
                    "component_code": line.component_code,
                    "component_name": line.component_name,
                    "quantity": line.quantity,
                    "weight_grams": line.weight_grams,
                    "datasheet_status": line.datasheet_status,
                    "cad_status": line.cad_status,
                    "size_status": line.size_status,
                    "sample_status": line.sample_status,
                    "supplier_reference": line.supplier_reference,
                }
                for line in self.line_ids.sorted(lambda item: (item.sequence, item.id))
            ],
        }

    def _assert_freeze_ready(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("Add at least one Bought Out Part before submission."))
        incomplete = self.line_ids.filtered(lambda line: not line.is_ready)
        if incomplete:
            raise ValidationError(
                _("Complete quantity, datasheet, CAD, size/envelope and physical-sample status for: %s")
                % ", ".join(incomplete.mapped("component_name"))
            )
        if not self.effective_date:
            raise ValidationError(_("Effective Date is required before the BOP is frozen."))
        if not (self.customer_signoff_name and self.customer_signoff_date):
            raise ValidationError(_("Customer sign-off name and date are required before BOP freeze."))

    def action_submit_review(self):
        for bop in self:
            if bop.state not in ("draft", "rejected"):
                raise UserError(_("Only a Draft or Rejected BOP can be submitted."))
            bop._assert_freeze_ready()
            if not bop.owner_designation_id._user_holds_for_project(self.env.user, bop.project_id):
                raise UserError(_("Only the BOP Owner Designation holder may submit it."))
            bop.with_context(hjig_bop_workflow=True).write({
                "state": "review", "submitted_by_id": self.env.user.id,
            })

    def action_freeze(self):
        for bop in self:
            if bop.state != "review":
                raise UserError(_("Only a BOP Under Review can be frozen."))
            bop._assert_freeze_ready()
            if not bop.approver_designation_id._user_holds_for_project(self.env.user, bop.project_id):
                raise UserError(_("Only the BOP Approver Designation holder may freeze it."))
            same_user_demo = (
                bop.submitted_by_id == self.env.user
                and staging_self_approval_demo_enabled(self.env)
            )
            if bop.submitted_by_id == self.env.user and not same_user_demo:
                raise ValidationError(_("The same user cannot submit and freeze the BOP."))
            previous = self.search([
                ("project_id", "=", bop.project_id.id),
                ("state", "=", "frozen"),
                ("id", "!=", bop.id),
            ])
            previous.with_context(hjig_bop_workflow=True).write({"state": "superseded"})
            payload = json.dumps(bop._snapshot_payload(), sort_keys=True, separators=(",", ":"))
            bop.with_context(hjig_bop_workflow=True).write({
                "state": "frozen",
                "frozen_by_id": self.env.user.id,
                "snapshot_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            })
            if same_user_demo:
                record_staging_demo_transition(
                    bop, "review", "frozen", "staging_demo_frozen"
                )

    def write(self, vals):
        controlled = set(self._fields) - CHATTER_FIELDS
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.state in ("frozen", "superseded")):
            allowed_supersede = set(vals) == {"state"} and vals.get("state") == "superseded"
            if not allowed_supersede:
                raise ValidationError(_("Frozen or superseded BOP records are read-only."))
        identity = {"project_id", "revision", "owner_designation_id", "approver_designation_id"}
        if identity.intersection(vals) and self.filtered(lambda rec: rec.state not in ("draft", "rejected")):
            raise ValidationError(_("BOP identity and authority are locked after submission."))
        if "state" in vals:
            if not self.env.context.get("hjig_bop_workflow"):
                raise ValidationError(_("Use the governed BOP actions to change workflow state."))
            allowed = {
                ("draft", "review"), ("rejected", "review"),
                ("review", "frozen"), ("review", "rejected"),
                ("frozen", "superseded"),
            }
            for bop in self:
                if bop.state != vals["state"] and (bop.state, vals["state"]) not in allowed:
                    raise ValidationError(_("Invalid BOP workflow transition."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.state not in ("draft", "rejected")):
            raise UserError(_("Only Draft or Rejected BOP records may be deleted."))
        return super().unlink()


class HjigBopLine(models.Model):
    _name = "hjig.bop.line"
    _description = "Bought Out Part Line"
    _order = "bop_id, sequence, id"

    bop_id = fields.Many2one("hjig.bop", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="bop_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    component_code = fields.Char(required=True)
    component_name = fields.Char(required=True)
    quantity = fields.Float(required=True, default=1.0)
    weight_grams = fields.Float()
    supplier_reference = fields.Char()
    datasheet_status = fields.Selection(
        [("pending", "Pending"), ("received", "Received"), ("not_applicable", "N/A")],
        required=True, default="pending",
    )
    cad_status = fields.Selection(
        [("pending", "Pending"), ("received", "Received"), ("not_applicable", "N/A")],
        required=True, default="pending",
    )
    size_status = fields.Selection(
        [("pending", "Pending"), ("envelope", "Envelope Only"), ("frozen", "Frozen")],
        required=True, default="pending",
    )
    sample_status = fields.Selection(
        [("pending", "Pending"), ("received", "Received")],
        required=True, default="pending",
    )
    notes = fields.Text()
    is_ready = fields.Boolean(compute="_compute_is_ready", store=True)

    _bop_component_unique = models.Constraint(
        "UNIQUE(bop_id, component_code)", "Component code must be unique within one BOP revision."
    )

    @api.depends("quantity", "datasheet_status", "cad_status", "size_status", "sample_status")
    def _compute_is_ready(self):
        for line in self:
            line.is_ready = bool(
                line.quantity > 0
                and line.datasheet_status != "pending"
                and line.cad_status != "pending"
                and line.size_status != "pending"
                and line.sample_status == "received"
            )

    @api.constrains("quantity", "weight_grams")
    def _check_positive_values(self):
        for line in self:
            if line.quantity <= 0 or line.weight_grams < 0:
                raise ValidationError(_("BOP quantity must be positive and weight cannot be negative."))

    def write(self, vals):
        if self.filtered(lambda line: line.bop_id.state not in ("draft", "rejected")):
            raise ValidationError(_("BOP lines are editable only while the register is Draft or Rejected."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.bop_id.state not in ("draft", "rejected")):
            raise UserError(_("BOP lines cannot be deleted after submission."))
        return super().unlink()


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [("hjig.bop", "BOP")]
