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
    source_route = fields.Selection(
        [
            ("customer_document", "Customer-Controlled BOP Document"),
            ("hongyi_guided", "Hongyi Guided BOP Capture"),
        ],
        required=True,
        default="hongyi_guided",
        tracking=True,
    )
    source_document_url = fields.Char(string="Source BOP Document URL", tracking=True)
    source_document_attachment = fields.Binary(
        string="Source BOP Document", attachment=True, copy=False
    )
    source_document_filename = fields.Char(copy=False)
    assembly_environment_reference = fields.Char(
        string="Assembly CAD / Environment Reference", tracking=True
    )
    assembly_reference_confirmed = fields.Boolean(
        string="BOP Data Matches Assembly Environment", tracking=True
    )
    responsibility_boundary_ack = fields.Boolean(
        string="Responsibility Boundary Acknowledged", tracking=True
    )
    change_control_ack = fields.Boolean(
        string="Post-Freeze Changes Require ECN", tracking=True
    )
    line_ids = fields.One2many("hjig.bop.line", "bop_id", string="Bought Out Parts")
    line_count = fields.Integer(compute="_compute_readiness")
    ready_line_count = fields.Integer(compute="_compute_readiness")
    completion_percent = fields.Float(compute="_compute_readiness")
    all_physical_samples_received = fields.Boolean(compute="_compute_readiness")
    stage_ready = fields.Boolean(compute="_compute_readiness")
    freeze_blockers = fields.Text(compute="_compute_readiness")
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
    customer_signoff_organization = fields.Char(string="Customer Organisation", tracking=True)
    customer_signoff_designation = fields.Char(tracking=True)
    customer_signoff_reference = fields.Char(
        string="Customer Signature / Approval Reference", tracking=True
    )
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
        "line_ids.source_ownership",
        "line_ids.drawing_reference",
        "line_ids.drawing_revision",
        "line_ids.impact_scope",
        "line_ids.assembly_impact",
        "line_ids.cad_assembly_match",
        "source_route",
        "source_document_url",
        "source_document_attachment",
        "assembly_environment_reference",
        "assembly_reference_confirmed",
        "responsibility_boundary_ack",
        "change_control_ack",
        "effective_date",
        "customer_signoff_name",
        "customer_signoff_organization",
        "customer_signoff_reference",
        "customer_signoff_date",
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
            blockers = []
            if not bop.line_ids:
                blockers.append(_("Add at least one Bought Out Part."))
            elif bop.line_ids.filtered(lambda line: not line.is_ready):
                blockers.append(_("Complete every component reference and readiness check."))
            if (
                bop.source_route == "customer_document"
                and not (bop.source_document_url or bop.source_document_attachment)
            ):
                blockers.append(_("Link or attach the customer-controlled BOP document."))
            if not bop.assembly_environment_reference:
                blockers.append(_("Enter the assembly CAD / environment reference."))
            if not bop.assembly_reference_confirmed:
                blockers.append(_("Confirm that BOP data matches the assembly environment."))
            if not bop.responsibility_boundary_ack:
                blockers.append(_("Acknowledge the Hongyi JIG responsibility boundary."))
            if not bop.change_control_ack:
                blockers.append(_("Acknowledge that post-freeze changes require an ECN."))
            if not bop.effective_date:
                blockers.append(_("Enter the effective date."))
            if not (
                bop.customer_signoff_name
                and bop.customer_signoff_organization
                and bop.customer_signoff_reference
                and bop.customer_signoff_date
            ):
                blockers.append(_("Complete customer acknowledgement and approval reference."))
            bop.stage_ready = not blockers
            bop.freeze_blockers = "\n".join("- %s" % blocker for blocker in blockers)

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
        for record in records:
            self.env["hjig.programme.run.artifact"]._link_native_record_across_gates(
                record, "FRM-004", "bop_id"
            )
        return records

    def _snapshot_payload(self):
        self.ensure_one()
        source_document_data = self.source_document_attachment or b""
        if isinstance(source_document_data, str):
            source_document_data = source_document_data.encode("utf-8")
        return {
            "project_id": self.project_id.id,
            "revision": self.revision,
            "effective_date": fields.Date.to_string(self.effective_date),
            "source_route": self.source_route,
            "source_document_url": self.source_document_url,
            "source_document_filename": self.source_document_filename,
            "source_document_sha256": (
                hashlib.sha256(source_document_data).hexdigest()
                if source_document_data else False
            ),
            "assembly_environment_reference": self.assembly_environment_reference,
            "assembly_reference_confirmed": self.assembly_reference_confirmed,
            "responsibility_boundary_ack": self.responsibility_boundary_ack,
            "change_control_ack": self.change_control_ack,
            "customer_signoff_name": self.customer_signoff_name,
            "customer_signoff_organization": self.customer_signoff_organization,
            "customer_signoff_designation": self.customer_signoff_designation,
            "customer_signoff_reference": self.customer_signoff_reference,
            "customer_signoff_date": fields.Date.to_string(self.customer_signoff_date),
            "lines": [
                {
                    "component_code": line.component_code,
                    "component_name": line.component_name,
                    "component_category": line.component_category,
                    "quantity": line.quantity,
                    "weight_grams": line.weight_grams,
                    "source_ownership": line.source_ownership,
                    "drawing_reference": line.drawing_reference,
                    "drawing_revision": line.drawing_revision,
                    "assembly_impact": line.assembly_impact,
                    "impact_scope": line.impact_scope,
                    "cad_assembly_match": line.cad_assembly_match,
                    "material_specification": line.material_specification,
                    "critical_tolerance": line.critical_tolerance,
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
        if not self.stage_ready:
            raise ValidationError(
                _("BOP cannot be submitted or frozen until these items are complete:\n%s")
                % self.freeze_blockers
            )

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
    bop_state = fields.Selection(related="bop_id.state", store=True, readonly=True)
    project_id = fields.Many2one(related="bop_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    component_image = fields.Image(string="Component Photo", max_width=1600, max_height=1600)
    sourcebridge_component_id = fields.Many2one(
        "hjig.sourcebridge.component",
        string="Linked SourceBridge Component",
        ondelete="restrict",
        domain="[('engagement_id.project_id', '=', project_id)]",
    )
    component_code = fields.Char(required=True)
    component_name = fields.Char(required=True)
    component_category = fields.Selection(
        [
            ("customer_supplied", "Customer-Supplied Component"),
            ("customer_nominated", "Customer-Nominated Outsourced Component"),
            ("catalogue", "Standard / Catalogue Component"),
            ("electromechanical", "Electro-Mechanical Item"),
            ("insert_fastener", "Insert / Fastener / Seal / Connector"),
            ("other", "Other Bought-Out Part"),
        ],
        required=True,
        default="customer_supplied",
    )
    quantity = fields.Float(required=True, default=1.0)
    weight_grams = fields.Float()
    supplier_reference = fields.Char()
    source_ownership = fields.Selection(
        [
            ("customer", "Customer"),
            ("customer_nominated", "Customer-Nominated Third Party"),
            ("third_party", "Third Party"),
            ("open_market", "Open Market"),
        ],
        required=True,
        default="customer",
    )
    drawing_reference = fields.Char(string="CAD / Drawing Reference")
    drawing_revision = fields.Char(string="CAD / Drawing Revision")
    assembly_impact = fields.Selection(
        [("yes", "Yes"), ("no", "No")],
        required=True,
        default="yes",
    )
    impact_scope = fields.Selection(
        [
            ("assembly", "Assembly"),
            ("fitment", "Fitment"),
            ("function", "Function"),
            ("validation", "Validation"),
            ("multiple", "Multiple / Combined"),
        ],
        required=True,
        default="assembly",
    )
    impact_description = fields.Text(string="Interface / Impact Notes")
    cad_assembly_match = fields.Selection(
        [
            ("pending", "Pending Verification"),
            ("confirmed", "Confirmed Match"),
            ("exception", "Exception / Risk Raised"),
        ],
        required=True,
        default="pending",
    )
    material_specification = fields.Char(string="Material / Specification")
    critical_tolerance = fields.Char(string="Critical Tolerance / Interface")
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

    @api.onchange("sourcebridge_component_id")
    def _onchange_sourcebridge_component_id(self):
        for line in self.filtered("sourcebridge_component_id"):
            component = line.sourcebridge_component_id
            line.component_code = component.code
            line.component_name = component.name
            line.quantity = component.quantity
            line.material_specification = component.specification
            line.component_category = (
                "catalogue" if component.category == "bought_out" else "other"
            )

    @api.depends(
        "component_code", "component_name", "quantity", "source_ownership",
        "drawing_reference", "drawing_revision", "impact_scope", "assembly_impact",
        "cad_assembly_match", "datasheet_status", "cad_status", "size_status", "sample_status",
    )
    def _compute_is_ready(self):
        for line in self:
            line.is_ready = bool(
                line.component_code
                and line.component_name
                and line.quantity > 0
                and line.source_ownership
                and line.drawing_reference
                and line.drawing_revision
                and line.impact_scope
                and line.assembly_impact
                and line.cad_assembly_match == "confirmed"
                and line.datasheet_status != "pending"
                and line.cad_status != "pending"
                and line.size_status == "frozen"
                and line.sample_status == "received"
            )

    @api.constrains("quantity", "weight_grams")
    def _check_positive_values(self):
        for line in self:
            if line.quantity <= 0 or line.weight_grams < 0:
                raise ValidationError(_("BOP quantity must be positive and weight cannot be negative."))

    def action_open_employee_detail(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bought Out Part Detail"),
            "res_model": "hjig.bop.line",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(self.env.ref("new_hongyijig_custom.view_hjig_bop_line_form").id, "form")],
            "target": "new",
        }

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
