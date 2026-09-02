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


class ProjectProject(models.Model):
    _inherit = "project.project"

    hjig_bop_ids = fields.One2many("hjig.bop", "project_id", string="BOP Registers")
    hjig_bop_count = fields.Integer(compute="_compute_hjig_bop_count")

    @api.depends("hjig_bop_ids")
    def _compute_hjig_bop_count(self):
        for project in self:
            project.hjig_bop_count = self.env["hjig.bop"].search_count([
                ("project_id", "=", project.id),
            ])

    def action_open_hjig_bop(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "new_hongyijig_custom.action_hjig_bop"
        )
        action.update({
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        })
        return action


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
    product_component_ids = fields.One2many(
        "hjig.bop.product.component", "bop_id", string="Product Components"
    )
    mapping_ids = fields.One2many("hjig.bop.mapping", "bop_id", string="Interface Mappings")
    product_component_count = fields.Integer(compute="_compute_governance_readiness")
    mapping_count = fields.Integer(compute="_compute_governance_readiness")
    confirmed_mapping_count = fields.Integer(compute="_compute_governance_readiness")

    # Gate 1: population sign-off.  These are business approvals, not employee accounts.
    population_declared_complete = fields.Boolean(string="Population Declared Complete by PC", tracking=True)
    population_coordinator_designation = fields.Char(string="Coordinator Designation", tracking=True)
    population_unresolved_count = fields.Integer(string="Unresolved BOP Count", default=0, tracking=True)
    population_evidence_reference = fields.Char(string="Source Documents / Evidence", tracking=True)
    population_evidence_url = fields.Char(string="Population Evidence Link", tracking=True)
    population_evidence_attachment = fields.Binary(
        string="Population Evidence File", attachment=True, copy=False
    )
    population_evidence_filename = fields.Char(copy=False)
    population_technical_reviewed = fields.Boolean(string="Technical Review Complete", tracking=True)
    population_technical_reviewer_designation = fields.Char(string="Technical Reviewer Designation", tracking=True)
    population_customer_signed = fields.Boolean(string="Customer Population Sign-off", tracking=True)
    population_customer_reference = fields.Char(string="Customer Population Approval Reference", tracking=True)
    population_customer_approval_url = fields.Char(string="Customer Population Approval Link", tracking=True)
    population_customer_approval_attachment = fields.Binary(
        string="Customer Population Approval File", attachment=True, copy=False
    )
    population_customer_approval_filename = fields.Char(copy=False)
    population_signed_at = fields.Datetime(readonly=True, copy=False)
    population_signed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    population_ready = fields.Boolean(compute="_compute_governance_readiness")

    # Gate 2/3: mapping coverage and design-input release.
    mapping_ready = fields.Boolean(compute="_compute_governance_readiness")
    design_release_ready = fields.Boolean(compute="_compute_governance_readiness")
    design_release_baseline = fields.Char(string="Design Input Baseline", tracking=True)
    design_release_recipients = fields.Text(string="Design Agency / Tooling Recipients", tracking=True)
    design_release_generated = fields.Boolean(readonly=True, copy=False, tracking=True)
    design_release_valid = fields.Boolean(readonly=True, copy=False, tracking=True)
    design_release_generated_at = fields.Datetime(readonly=True, copy=False)
    design_release_generated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    design_release_snapshot_json = fields.Text(readonly=True, copy=False)
    design_release_snapshot_hash = fields.Char(readonly=True, copy=False, tracking=True)

    # Gate 4: final design freeze acknowledgement.
    design_freeze_customer_confirmed = fields.Boolean(string="Customer Design Freeze Sign-off", tracking=True)
    design_freeze_customer_reference = fields.Char(string="Customer Design Freeze Reference", tracking=True)
    design_freeze_customer_approval_url = fields.Char(string="Design Freeze Approval Link", tracking=True)
    design_freeze_customer_approval_attachment = fields.Binary(
        string="Design Freeze Approval File", attachment=True, copy=False
    )
    design_freeze_customer_approval_filename = fields.Char(copy=False)
    design_freeze_internal_approver = fields.Char(string="Internal Approver Designation", tracking=True)
    governance_blockers = fields.Text(compute="_compute_governance_readiness")
    line_count = fields.Integer(compute="_compute_readiness")
    ready_line_count = fields.Integer(compute="_compute_readiness")
    completion_percent = fields.Float(compute="_compute_readiness")
    data_completion_percent = fields.Float(compute="_compute_readiness")
    physical_sample_percent = fields.Float(compute="_compute_readiness")
    mapping_completion_percent = fields.Float(compute="_compute_readiness")
    approval_completion_percent = fields.Float(compute="_compute_readiness")
    all_physical_samples_received = fields.Boolean(
        string="All Required Physical Quantities Verified", compute="_compute_readiness"
    )
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
    revision_reason = fields.Selection(
        [("initial", "Initial IG-01 Baseline"), ("post_a011", "Post A-011 Design Revision"),
         ("ecn", "Engineering Change / ECN")],
        required=True, default="initial", tracking=True,
    )
    revision_change_reason = fields.Text(string="Revision / ECN Reason", tracking=True)
    next_revision_reason = fields.Selection(
        [("post_a011", "Post A-011 Design Revision"), ("ecn", "Engineering Change / ECN")],
        string="New Revision Trigger", default="post_a011", copy=False, tracking=True,
    )
    supersedes_id = fields.Many2one("hjig.bop", readonly=True, copy=False, ondelete="restrict")
    superseded_by_id = fields.Many2one("hjig.bop", readonly=True, copy=False, ondelete="restrict")
    notes = fields.Text()

    _project_revision_unique = models.Constraint(
        "UNIQUE(project_id, revision)",
        "This BOP revision already exists for the project.",
    )

    @api.depends(
        "line_ids",
        "line_ids.is_ready",
        "line_ids.applicability",
        "line_ids.required_quantity",
        "line_ids.verified_usable_quantity",
        "line_ids.verification_evidence",
        "line_ids.verification_attachment",
        "line_ids.lock_status",
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
        "product_component_ids.maturity",
        "mapping_ids.state",
        "mapping_ids.is_exception",
        "mapping_ids.exception_ready",
        "mapping_ids.maturity",
        "mapping_ids.technical_confirmed",
        "mapping_ids.customer_signed",
        "mapping_ids.customer_reference",
        "mapping_ids.evidence_reference",
        "mapping_ids.accountable_designation",
        "mapping_ids.due_date",
        "mapping_ids.participant_ids.component_id",
        "population_declared_complete",
        "population_coordinator_designation",
        "population_unresolved_count",
        "population_evidence_reference",
        "population_evidence_url",
        "population_evidence_attachment",
        "population_technical_reviewed",
        "population_technical_reviewer_designation",
        "population_customer_signed",
        "population_customer_reference",
        "population_customer_approval_url",
        "population_customer_approval_attachment",
        "design_release_baseline",
        "design_release_recipients",
        "design_release_generated",
        "design_release_valid",
        "design_freeze_customer_confirmed",
        "design_freeze_customer_reference",
        "design_freeze_customer_approval_url",
        "design_freeze_customer_approval_attachment",
        "design_freeze_internal_approver",
    )
    def _compute_readiness(self):
        for bop in self:
            bop.line_count = len(bop.line_ids)
            ready = bop.line_ids.filtered("is_ready")
            bop.ready_line_count = len(ready)
            applicable = bop.line_ids.filtered(lambda line: line.applicability == "applicable")
            total = len(applicable)
            data_ready = applicable.filtered(lambda line: line._bop_data_ready())
            sample_ready = applicable.filtered(lambda line: line._bop_sample_ready())
            approval_ready = applicable.filtered(lambda line: line._bop_approval_ready())
            active_mappings = bop.mapping_ids.filtered(lambda mapping: mapping.state == "active")
            covered_line_ids = set(active_mappings.filtered(
                lambda mapping: mapping.exception_ready if mapping.is_exception else bool(mapping.participant_ids)
            ).mapped("bop_line_id").ids)
            bop.data_completion_percent = 100.0 * len(data_ready) / total if total else 0.0
            bop.physical_sample_percent = 100.0 * len(sample_ready) / total if total else 0.0
            bop.mapping_completion_percent = (
                100.0 * len(applicable.filtered(lambda line: line.id in covered_line_ids)) / total
                if total else 0.0
            )
            bop.approval_completion_percent = 100.0 * len(approval_ready) / total if total else 0.0
            bop.completion_percent = sum((
                bop.data_completion_percent, bop.physical_sample_percent,
                bop.mapping_completion_percent, bop.approval_completion_percent,
            )) / 4.0
            bop.all_physical_samples_received = bool(applicable) and all(
                line.required_quantity > 0
                and line.verified_usable_quantity >= line.required_quantity
                and line._bop_sample_evidence_ready()
                for line in applicable
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
            if not (bop.population_evidence_url or bop.population_evidence_attachment):
                blockers.append(_("Attach or link the reviewed BOP population evidence."))
            if not (
                bop.population_customer_approval_url
                or bop.population_customer_approval_attachment
            ):
                blockers.append(_("Attach or link the customer population approval evidence."))
            if applicable.filtered(lambda line: not line._bop_sample_evidence_ready()):
                blockers.append(_("Attach or link physical sample verification evidence for every applicable BOP."))
            if not bop.design_release_generated or not bop.design_release_valid:
                blockers.append(_("Generate a current Design Input Release package."))
            if not (
                bop.design_freeze_customer_confirmed
                and bop.design_freeze_customer_reference
                and bop.design_freeze_internal_approver
            ):
                blockers.append(_("Complete final customer Design Freeze sign-off and internal approver."))
            if not (
                bop.design_freeze_customer_approval_url
                or bop.design_freeze_customer_approval_attachment
            ):
                blockers.append(_("Attach or link the final customer Design Freeze approval."))
            bop.stage_ready = not blockers
            bop.freeze_blockers = "\n".join("- %s" % blocker for blocker in blockers)

    @api.depends(
        "line_ids", "line_ids.applicability", "line_ids.lock_status",
        "product_component_ids", "product_component_ids.maturity",
        "mapping_ids", "mapping_ids.state", "mapping_ids.is_exception",
        "mapping_ids.exception_ready", "mapping_ids.maturity",
        "mapping_ids.technical_confirmed", "mapping_ids.customer_signed",
        "mapping_ids.customer_reference", "mapping_ids.evidence_reference",
        "mapping_ids.accountable_designation", "mapping_ids.due_date",
        "mapping_ids.participant_ids.component_id",
        "population_declared_complete", "population_coordinator_designation",
        "population_unresolved_count", "population_evidence_reference",
        "population_evidence_url", "population_evidence_attachment",
        "population_technical_reviewed", "population_technical_reviewer_designation",
        "population_customer_signed", "population_customer_reference",
        "population_customer_approval_url", "population_customer_approval_attachment",
        "design_release_baseline", "design_release_recipients",
        "design_release_generated", "design_release_valid",
    )
    def _compute_governance_readiness(self):
        for bop in self:
            active_mappings = bop.mapping_ids.filtered(lambda m: m.state == "active")
            applicable_items = bop.line_ids.filtered(lambda line: line.applicability == "applicable")
            bop.product_component_count = len(bop.product_component_ids)
            bop.mapping_count = len(active_mappings.filtered(lambda m: not m.is_exception))
            bop.confirmed_mapping_count = len(active_mappings.filtered(
                lambda m: not m.is_exception and m.maturity == "confirmed"
            ))
            bop.population_ready = bool(
                bop.population_declared_complete
                and bop.population_coordinator_designation
                and bop.population_unresolved_count == 0
                and bop.population_evidence_reference
                and (bop.population_evidence_url or bop.population_evidence_attachment)
                and bop.population_technical_reviewed
                and bop.population_technical_reviewer_designation
                and bop.population_customer_signed
                and bop.population_customer_reference
                and (bop.population_customer_approval_url or bop.population_customer_approval_attachment)
            )
            covered_item_ids = set(active_mappings.filtered(
                lambda m: m.exception_ready if m.is_exception else bool(m.participant_ids)
            ).mapped("bop_line_id").ids)
            bop.mapping_ready = bool(
                bop.population_ready
                and applicable_items
                and all(line.id in covered_item_ids for line in applicable_items)
            )
            design_mappings = active_mappings.filtered(lambda m: not m.is_exception)
            confirmed_mappings = design_mappings.filtered("is_confirmed_ready")
            participant_components = active_mappings.participant_ids.mapped("component_id")
            components_confirmed = bool(participant_components) and all(
                component.maturity == "confirmed" for component in participant_components
            )
            bop.design_release_ready = bool(
                bop.mapping_ready
                and applicable_items
                and all(line.lock_status == "locked" for line in applicable_items)
                and design_mappings
                and len(confirmed_mappings) == len(design_mappings)
                and components_confirmed
                and bop.design_release_baseline
                and bop.design_release_recipients
            )
            blockers = []
            if not bop.population_ready:
                blockers.append(_("Complete BOP population declaration, evidence, technical review and customer sign-off."))
            if not bop.mapping_ready:
                blockers.append(_("Give every applicable BOP a component mapping or a technically approved exception."))
            if applicable_items.filtered(lambda line: line.lock_status != "locked"):
                blockers.append(_("Lock every applicable BOP item after technical, quantity, document and customer checks."))
            if design_mappings.filtered(lambda mapping: not mapping.is_confirmed_ready):
                blockers.append(_("Confirm every design-affecting mapping with evidence and customer approval."))
            if participant_components and not components_confirmed:
                blockers.append(_("Confirm the maturity of every mapped product/meeting component."))
            if not bop.design_release_baseline or not bop.design_release_recipients:
                blockers.append(_("Enter the design-input baseline and recipients."))
            if bop.design_release_generated and not bop.design_release_valid:
                blockers.append(_("The prior design-input release is stale; generate a new release."))
            bop.governance_blockers = "\n".join("- %s" % item for item in blockers)

    def _invalidate_design_release(self):
        for bop in self.filtered(lambda record: record.design_release_generated and record.design_release_valid):
            super(HjigBop, bop.with_context(hjig_bop_release_invalidation=True)).write({
                "design_release_valid": False,
            })

    def action_sign_population(self):
        for bop in self:
            if not bop.population_ready:
                raise ValidationError(_("Population sign-off is incomplete. Review the Gate 1 blockers."))
            bop.write({"population_signed_at": fields.Datetime.now(), "population_signed_by_id": self.env.user.id})

    def action_import_mould_planning_parts(self):
        for bop in self:
            if bop.state not in ("draft", "rejected"):
                raise UserError(_("Mould Planning parts can be imported only while the BOP register is editable."))
            parts = self.env["x_mould_part"].search([
                ("x_mould_id.x_project_id", "=", bop.project_id.id),
            ])
            existing_part_ids = set(bop.product_component_ids.mapped("mould_part_id").ids)
            existing_codes = set(bop.product_component_ids.mapped("code"))
            values = []
            for part in parts.filtered(
                lambda record: record.id not in existing_part_ids
                and (record.x_part_number or "PC-%s" % record.id) not in existing_codes
            ):
                values.append((0, 0, {
                    "code": part.x_part_number or "PC-%s" % part.id,
                    "name": part.x_name,
                    "maturity": "tentative",
                    "mould_part_id": part.id,
                }))
            if values:
                bop.write({"product_component_ids": values})
            else:
                bop.message_post(body=_("No new Mould Planning parts were available to import."))

    def action_generate_design_release(self):
        for bop in self:
            if not bop.design_release_ready:
                raise ValidationError(_("Design input cannot be released:\n%s") % bop.governance_blockers)
            release_payload = json.dumps(
                bop._snapshot_payload(), sort_keys=True, separators=(",", ":")
            )
            bop.with_context(hjig_bop_release_action=True).write({
                "design_release_generated": True,
                "design_release_valid": True,
                "design_release_generated_at": fields.Datetime.now(),
                "design_release_generated_by_id": self.env.user.id,
                "design_release_snapshot_json": release_payload,
                "design_release_snapshot_hash": hashlib.sha256(
                    release_payload.encode("utf-8")
                ).hexdigest(),
            })

    def action_create_controlled_revision(self):
        self.ensure_one()
        if self.state != "frozen":
            raise UserError(_("A controlled revision can be created only from a Frozen BOP."))
        if not self.revision_change_reason:
            raise ValidationError(_("Enter the revision / ECN reason before creating a new revision."))
        numbers = []
        for revision in self.search([("project_id", "=", self.project_id.id)]).mapped("revision"):
            if revision and revision.upper().startswith("R") and revision[1:].isdigit():
                numbers.append(int(revision[1:]))
        next_revision = "R%02d" % (max(numbers, default=-1) + 1)
        new_record = self.copy({
            "state": "draft",
            "revision": next_revision,
            "revision_reason": self.next_revision_reason or "post_a011",
            "revision_change_reason": self.revision_change_reason,
            "supersedes_id": self.id,
            "population_declared_complete": False,
            "population_technical_reviewed": False,
            "population_customer_signed": False,
            "population_signed_at": False,
            "population_signed_by_id": False,
            "design_release_generated": False,
            "design_release_valid": False,
            "design_release_generated_at": False,
            "design_release_generated_by_id": False,
            "design_release_snapshot_json": False,
            "design_release_snapshot_hash": False,
            "design_freeze_customer_confirmed": False,
            "design_freeze_customer_reference": False,
            "design_freeze_customer_approval_url": False,
            "design_freeze_customer_approval_attachment": False,
            "design_freeze_customer_approval_filename": False,
            "design_freeze_internal_approver": False,
            "submitted_by_id": False,
            "frozen_by_id": False,
            "snapshot_hash": False,
            "line_ids": False,
            "product_component_ids": False,
            "mapping_ids": False,
        })
        line_map = {}
        for line in self.line_ids.sorted(lambda item: (item.sequence, item.id)):
            copied_line = line.copy({
                "bop_id": new_record.id,
                "lock_status": "draft",
                "locked_by_id": False,
                "locked_at": False,
                "changed_after_lock": False,
                "customer_item_freeze": False,
                "customer_item_freeze_reference": False,
                "customer_item_freeze_date": False,
            })
            line_map[line.id] = copied_line
        component_map = {}
        for component in self.product_component_ids.sorted(lambda item: (item.sequence, item.id)):
            copied_component = component.copy({
                "bop_id": new_record.id, "maturity": "tentative",
            })
            component_map[component.id] = copied_component
        for mapping in self.mapping_ids.filtered(lambda item: item.state == "active").sorted(
            lambda item: (item.sequence, item.id)
        ):
            copied_mapping = mapping.copy({
                "bop_id": new_record.id,
                "bop_line_id": line_map[mapping.bop_line_id.id].id,
                "participant_ids": False,
                "state": "active",
                "maturity": "tentative",
                "technical_confirmed": False,
                "customer_signed": False,
            })
            for participant in mapping.participant_ids.sorted(lambda item: (item.sequence, item.id)):
                participant.copy({
                    "mapping_id": copied_mapping.id,
                    "component_id": component_map[participant.component_id.id].id,
                })
        self.with_context(hjig_bop_revision_link=True).write({"superseded_by_id": new_record.id})
        open_requirements = self.env["hjig.programme.run.artifact"].search([
            ("project_id", "=", self.project_id.id),
            ("artifact_code", "=", "FRM-004"),
            ("run_gate_id.state", "!=", "approved"),
        ])
        open_requirements.write({"bop_id": new_record.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Controlled BOP Revision"),
            "res_model": "hjig.bop",
            "res_id": new_record.id,
            "view_mode": "form",
            "target": "current",
        }

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
            "population": {
                "declared_complete": self.population_declared_complete,
                "coordinator_designation": self.population_coordinator_designation,
                "unresolved_count": self.population_unresolved_count,
                "evidence_reference": self.population_evidence_reference,
                "evidence_url": self.population_evidence_url,
                "technical_reviewed": self.population_technical_reviewed,
                "technical_reviewer_designation": self.population_technical_reviewer_designation,
                "customer_signed": self.population_customer_signed,
                "customer_reference": self.population_customer_reference,
                "customer_approval_url": self.population_customer_approval_url,
            },
            "design_release": {
                "baseline": self.design_release_baseline,
                "recipients": self.design_release_recipients,
                "generated_at": fields.Datetime.to_string(self.design_release_generated_at),
            },
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
                    "manufacturer": line.manufacturer,
                    "model_part_number": line.model_part_number,
                    "item_revision": line.item_revision,
                    "applicability": line.applicability,
                    "sourcing_responsibility": line.sourcing_responsibility,
                    "hongyi_commercially_responsible": line.hongyi_commercially_responsible,
                    "supplier_status": line.supplier_status,
                    "commercial_status": line.commercial_status,
                    "drawing_2d": [line.drawing_2d_status, line.drawing_2d_reference, line.drawing_2d_revision],
                    "model_3d": [line.model_3d_status, line.model_3d_reference, line.model_3d_revision],
                    "datasheet": [line.datasheet_status, line.datasheet_reference, line.datasheet_revision],
                    "technical_validation": line.technical_validation,
                    "validator_designation": line.validator_designation,
                    "required_quantity": line.required_quantity,
                    "verified_usable_quantity": line.verified_usable_quantity,
                    "verification_evidence": line.verification_evidence,
                    "customer_item_freeze_reference": line.customer_item_freeze_reference,
                    "lock_status": line.lock_status,
                }
                for line in self.line_ids.sorted(lambda item: (item.sequence, item.id))
            ],
            "product_components": [
                {
                    "code": component.code, "name": component.name,
                    "maturity": component.maturity,
                    "is_meeting_component": component.is_meeting_component,
                    "origin": component.origin, "design_scope": component.design_scope,
                    "tooling_scope": component.tooling_scope,
                    "mould_part_id": component.mould_part_id.id,
                }
                for component in self.product_component_ids.sorted(lambda item: (item.sequence, item.id))
            ],
            "mappings": [
                {
                    "code": mapping.code, "bop_line": mapping.bop_line_id.component_code,
                    "is_exception": mapping.is_exception, "exception_reason": mapping.exception_reason,
                    "topology": mapping.topology, "maturity": mapping.maturity,
                    "participants": [
                        [participant.component_id.code, participant.role, participant.quantity, participant.position]
                        for participant in mapping.participant_ids.sorted(lambda item: (item.sequence, item.id))
                    ],
                    "evidence_reference": mapping.evidence_reference,
                    "technical_confirmed": mapping.technical_confirmed,
                    "customer_reference": mapping.customer_reference,
                }
                for mapping in self.mapping_ids.filtered(lambda record: record.state == "active").sorted(
                    lambda item: (item.sequence, item.id)
                )
            ],
        }

    def _assert_freeze_ready(self):
        self.ensure_one()
        if not self.stage_ready:
            raise ValidationError(
                _("BOP cannot be submitted or frozen until these items are complete:\n%s")
                % self.freeze_blockers
            )
        if not self.design_release_generated or not self.design_release_valid:
            raise ValidationError(_("Generate a current Design Input Release before final BOP freeze."))
        if not (
            self.design_freeze_customer_confirmed
            and self.design_freeze_customer_reference
            and self.design_freeze_internal_approver
        ):
            raise ValidationError(_("Complete customer Design Freeze sign-off and internal approver."))

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
            previous.with_context(hjig_bop_workflow=True).write({
                "state": "superseded", "superseded_by_id": bop.id,
            })
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
        protected_release_fields = {
            "design_release_generated", "design_release_valid", "design_release_generated_at",
            "design_release_generated_by_id", "design_release_snapshot_json",
            "design_release_snapshot_hash",
        }
        if protected_release_fields.intersection(vals) and not (
            self.env.context.get("hjig_bop_release_action")
            or self.env.context.get("hjig_bop_release_invalidation")
        ):
            raise ValidationError(_("Use the governed Design Input Release action."))
        release_fields = {
            "line_ids", "product_component_ids", "mapping_ids",
            "source_route", "source_document_url", "source_document_attachment",
            "population_evidence_url", "population_evidence_attachment",
            "population_customer_approval_url", "population_customer_approval_attachment",
            "assembly_environment_reference", "assembly_reference_confirmed",
            "population_declared_complete", "population_coordinator_designation",
            "population_unresolved_count", "population_evidence_reference",
            "population_technical_reviewed", "population_technical_reviewer_designation",
            "population_customer_signed", "population_customer_reference",
            "design_release_baseline", "design_release_recipients",
        }
        invalidate = bool(release_fields.intersection(vals)) and not (
            self.env.context.get("hjig_bop_release_action")
            or self.env.context.get("hjig_bop_release_invalidation")
        )
        controlled = set(self._fields) - CHATTER_FIELDS
        if controlled.intersection(vals) and self.filtered(lambda rec: rec.state in ("frozen", "superseded")):
            allowed_revision_metadata = (
                set(vals).issubset({"next_revision_reason", "revision_change_reason"})
                and bool(self)
                and all(rec.state == "frozen" for rec in self)
            )
            allowed_supersede = (
                set(vals).issubset({"state", "superseded_by_id"})
                and vals.get("state", "superseded") == "superseded"
            ) or (
                set(vals) == {"superseded_by_id"}
                and self.env.context.get("hjig_bop_revision_link")
            )
            if not allowed_supersede and not allowed_revision_metadata:
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
        result = super().write(vals)
        if invalidate:
            self._invalidate_design_release()
        return result

    def unlink(self):
        if self.filtered(lambda rec: rec.state not in ("draft", "rejected")):
            raise UserError(_("Only Draft or Rejected BOP records may be deleted."))
        return super().unlink()


class HjigBopLine(models.Model):
    _name = "hjig.bop.line"
    _description = "Bought Out Part Line"
    _rec_name = "component_name"
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
    customer_part_number = fields.Char(string="Customer Part No.")
    manufacturer = fields.Char()
    model_part_number = fields.Char(string="Model / Part No.")
    item_revision = fields.Char(string="Item Revision")
    applicability = fields.Selection(
        [("applicable", "Applicable"), ("proposed_na", "Propose Not Applicable"),
         ("na_approved", "Not Applicable (Approved)")],
        required=True, default="applicable",
    )
    na_reason = fields.Text(string="N/A Reason")
    na_evidence = fields.Char(string="N/A Evidence")
    na_approved_by_designation = fields.Char(string="N/A Approved By Designation")
    component_category = fields.Selection(
        [
            ("mechanical", "Mechanical"),
            ("electronic", "Electronic"),
            ("label", "Label"),
            ("packaging", "Packaging"),
            ("customer_specific", "Customer-Specific"),
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
    sourcing_responsibility = fields.Selection(
        [("customer_supplied", "Customer Supplied"), ("hongyi_sourced", "Hongyi Sourced"),
         ("design_agency_sourced", "Design Agency Sourced"),
         ("tooling_agency_sourced", "Tooling Agency Sourced"), ("other", "Other")],
        required=True, default="customer_supplied",
    )
    hongyi_commercially_responsible = fields.Boolean(string="Hongyi Commercially Responsible")
    supplier_status = fields.Selection(
        [("not_identified", "Not Identified"), ("under_evaluation", "Under Evaluation"),
         ("finalized", "Finalized")], default="not_identified",
    )
    quote_reference = fields.Char()
    unit_price = fields.Monetary()
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    commercial_status = fields.Selection(
        [("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected")],
        default="pending",
    )
    commercial_pending_reason = fields.Text()
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
        [("pending", "Pending"), ("available", "Available"), ("na", "N/A"),
         ("received", "Received (Legacy)"), ("not_applicable", "N/A (Legacy)")],
        required=True, default="pending",
    )
    drawing_2d_status = fields.Selection(
        [("pending", "Pending"), ("available", "Available"), ("na", "N/A")], default="pending"
    )
    drawing_2d_reference = fields.Char(string="2D Reference")
    drawing_2d_revision = fields.Char(string="2D Revision")
    drawing_2d_na_reason = fields.Char(string="2D N/A Reason")
    model_3d_status = fields.Selection(
        [("pending", "Pending"), ("available", "Available"), ("na", "N/A")], default="pending"
    )
    model_3d_reference = fields.Char(string="3D Reference")
    model_3d_revision = fields.Char(string="3D Revision")
    model_3d_na_reason = fields.Char(string="3D N/A Reason")
    datasheet_reference = fields.Char()
    datasheet_revision = fields.Char()
    datasheet_na_reason = fields.Char(string="Datasheet N/A Reason")
    technical_validation = fields.Selection(
        [("pending", "Pending"), ("validated", "Validated")], default="pending"
    )
    validator_designation = fields.Char()
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
    required_quantity = fields.Float(string="Required Qty (Design / Trial)")
    ordered_quantity = fields.Float(string="Ordered / Committed Qty")
    received_quantity = fields.Float()
    verified_usable_quantity = fields.Float()
    required_by_date = fields.Date()
    custody_location = fields.Char(string="Location / Custodian")
    verification_date = fields.Date()
    verification_evidence = fields.Char()
    verification_attachment = fields.Binary(
        string="Sample Verification Evidence File", attachment=True, copy=False
    )
    verification_attachment_filename = fields.Char(copy=False)
    alternate_ids = fields.One2many("hjig.bop.alternate", "bop_line_id", string="Approved Alternates")
    customer_item_freeze = fields.Boolean(string="Customer Freeze Confirmed on Item")
    customer_item_freeze_reference = fields.Char(string="Customer Freeze Reference")
    customer_item_freeze_date = fields.Date(string="Customer Freeze Date")
    lock_status = fields.Selection(
        [("draft", "Draft"), ("locked", "Locked"), ("reopened_via_ecn", "Reopened via ECN")],
        required=True, default="draft", copy=False,
    )
    locked_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    locked_at = fields.Datetime(readonly=True, copy=False)
    changed_after_lock = fields.Boolean(readonly=True, copy=False)
    change_reason = fields.Text(readonly=True, copy=False)
    ecn_required = fields.Selection([("yes", "Yes"), ("no", "No")], copy=False)
    ecn_reference = fields.Char(copy=False)
    notes = fields.Text()
    is_ready = fields.Boolean(compute="_compute_is_ready", store=True)

    def _bop_data_ready(self):
        self.ensure_one()
        if self.applicability == "na_approved":
            return bool(self.na_reason and self.na_evidence and self.na_approved_by_designation)
        return bool(
            self.component_code and self.component_name and self.quantity > 0
            and self.manufacturer and self.model_part_number and self.item_revision
            and self.source_ownership and self.technical_validation == "validated"
            and self.validator_designation and self.drawing_2d_status in ("available", "na")
            and self.model_3d_status in ("available", "na")
            and self.datasheet_status in ("available", "received", "na", "not_applicable")
        )

    def _bop_sample_evidence_ready(self):
        self.ensure_one()
        evidence = (self.verification_evidence or "").strip().lower()
        return bool(self.verification_attachment or evidence.startswith(("http://", "https://")))

    def _bop_sample_ready(self):
        self.ensure_one()
        return bool(
            self.required_quantity > 0
            and self.verified_usable_quantity >= self.required_quantity
            and self._bop_sample_evidence_ready()
        )

    def _bop_approval_ready(self):
        self.ensure_one()
        return bool(self.customer_item_freeze and self.customer_item_freeze_reference)

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
        "applicability", "manufacturer", "model_part_number", "item_revision",
        "hongyi_commercially_responsible", "supplier_status", "commercial_status",
        "drawing_2d_status", "drawing_2d_reference", "drawing_2d_revision", "drawing_2d_na_reason",
        "model_3d_status", "model_3d_reference", "model_3d_revision", "model_3d_na_reason",
        "datasheet_reference", "datasheet_revision", "datasheet_na_reason",
        "technical_validation", "validator_designation", "required_quantity",
        "verified_usable_quantity", "verification_evidence", "verification_attachment",
        "customer_item_freeze", "customer_item_freeze_reference",
    )
    def _compute_is_ready(self):
        for line in self:
            def document_ready(status, reference, revision, na_reason):
                return bool(
                    (status == "available" and reference and revision)
                    or (status == "na" and na_reason)
                )

            if line.applicability == "na_approved":
                line.is_ready = bool(line.na_reason and line.na_evidence and line.na_approved_by_designation)
                continue
            commercial_ready = bool(
                not line.hongyi_commercially_responsible
                or (line.supplier_status == "finalized" and line.commercial_status == "accepted")
            )
            controlled_documents_ready = bool(
                document_ready(line.drawing_2d_status, line.drawing_2d_reference,
                               line.drawing_2d_revision, line.drawing_2d_na_reason)
                and document_ready(line.model_3d_status, line.model_3d_reference,
                                   line.model_3d_revision, line.model_3d_na_reason)
                and document_ready(
                    "available" if line.datasheet_status == "received" else
                    ("na" if line.datasheet_status == "not_applicable" else line.datasheet_status),
                    line.datasheet_reference, line.datasheet_revision, line.datasheet_na_reason
                )
            )
            line.is_ready = bool(
                line.applicability == "applicable"
                and line.component_code
                and line.component_name
                and line.quantity > 0
                and line.manufacturer
                and line.model_part_number
                and line.item_revision
                and commercial_ready
                and controlled_documents_ready
                and line.technical_validation == "validated"
                and line.validator_designation
                and line.required_quantity > 0
                and line.verified_usable_quantity >= line.required_quantity
                and line._bop_sample_evidence_ready()
                and line.customer_item_freeze
                and line.customer_item_freeze_reference
                and line.source_ownership
            )

    def action_lock_item(self):
        for line in self:
            if line.applicability != "applicable":
                raise ValidationError(_("Only applicable BOP items can be locked."))
            if not line.is_ready:
                raise ValidationError(_("Complete identity, commercial responsibility, controlled documents, physical verification and customer freeze before locking."))
            line.with_context(hjig_bop_item_workflow=True).write({
                "lock_status": "locked", "locked_by_id": self.env.user.id,
                "locked_at": fields.Datetime.now(), "changed_after_lock": False,
            })

    def action_reopen_via_ecn(self):
        for line in self:
            if line.lock_status != "locked":
                raise UserError(_("Only a locked BOP item can be reopened."))
            if not line.change_reason or not line.ecn_reference:
                raise ValidationError(_("Enter the change reason and ECN reference before reopening."))
            line.with_context(hjig_bop_item_workflow=True).write({
                "lock_status": "reopened_via_ecn", "changed_after_lock": True,
            })
            line.bop_id._invalidate_design_release()

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("bop_id")._invalidate_design_release()
        return records

    def write(self, vals):
        if "lock_status" in vals and not self.env.context.get("hjig_bop_item_workflow"):
            raise ValidationError(_("Use Lock Item or Reopen via ECN to change item lock status."))
        if self.filtered(lambda line: line.bop_id.state not in ("draft", "rejected")):
            raise ValidationError(_("BOP lines are editable only while the register is Draft or Rejected."))
        allowed_locked_fields = {"change_reason", "ecn_reference", "ecn_required", "lock_status", "changed_after_lock"}
        if (
            self.filtered(lambda line: line.lock_status == "locked")
            and set(vals) - allowed_locked_fields
            and not self.env.context.get("hjig_bop_item_workflow")
        ):
            raise ValidationError(_("A locked BOP item must be reopened via ECN before technical data can change."))
        result = super().write(vals)
        self.mapped("bop_id")._invalidate_design_release()
        return result

    def unlink(self):
        if self.filtered(lambda line: line.bop_id.state not in ("draft", "rejected")):
            raise UserError(_("BOP lines cannot be deleted after submission."))
        bops = self.mapped("bop_id")
        result = super().unlink()
        bops._invalidate_design_release()
        return result


class HjigBopAlternate(models.Model):
    _name = "hjig.bop.alternate"
    _description = "Approved BOP Alternate"
    _order = "bop_line_id, sequence, id"

    sequence = fields.Integer(default=10)
    bop_line_id = fields.Many2one("hjig.bop.line", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="bop_line_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    manufacturer = fields.Char(required=True)
    part_number = fields.Char(required=True)
    revision = fields.Char(required=True)
    evidence_reference = fields.Char(required=True)
    approved_by_designation = fields.Char(required=True)
    approval_date = fields.Date(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        lines = self.env["hjig.bop.line"].browse([vals.get("bop_line_id") for vals in vals_list])
        if lines.filtered(lambda line: line.lock_status == "locked"):
            raise ValidationError(_("Reopen the BOP item via ECN before changing approved alternates."))
        return super().create(vals_list)


class HjigBopProductComponent(models.Model):
    _name = "hjig.bop.product.component"
    _description = "BOP Product Component"
    _order = "bop_id, sequence, id"

    sequence = fields.Integer(default=10)
    bop_id = fields.Many2one("hjig.bop", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="bop_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    maturity = fields.Selection([("tentative", "Tentative"), ("confirmed", "Confirmed")], required=True, default="tentative")
    is_meeting_component = fields.Boolean(string="Meeting / Interface Component")
    origin = fields.Selection(
        [("new_design", "New Design"), ("customer_existing", "Customer Existing"),
         ("externally_sourced", "Externally Sourced")], required=True, default="new_design"
    )
    design_scope = fields.Selection(
        [("in_scope", "In Scope"), ("reference_only", "Reference Only"),
         ("out_of_scope", "Out of Scope")], required=True, default="in_scope"
    )
    tooling_scope = fields.Selection(
        [("in_scope", "In Scope"), ("out_of_scope", "Out of Scope")],
        required=True, default="in_scope"
    )
    mould_part_id = fields.Many2one("x_mould_part", string="Mould Planning Part", ondelete="restrict",
                                   domain="[('x_mould_id.x_project_id', '=', project_id)]")
    notes = fields.Text()

    _bop_product_component_unique = models.Constraint(
        "UNIQUE(bop_id, code)", "Product component code must be unique within one BOP revision."
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("bop_id")._invalidate_design_release()
        return records

    def write(self, vals):
        if self.filtered(lambda record: record.bop_id.state not in ("draft", "rejected")):
            raise ValidationError(_("Product components are editable only while the BOP register is Draft or Rejected."))
        result = super().write(vals)
        self.mapped("bop_id")._invalidate_design_release()
        return result

    def unlink(self):
        bops = self.mapped("bop_id")
        result = super().unlink()
        bops._invalidate_design_release()
        return result


class HjigBopMapping(models.Model):
    _name = "hjig.bop.mapping"
    _description = "BOP to Product Component Interface Mapping"
    _order = "bop_id, sequence, id"

    sequence = fields.Integer(default=10)
    bop_id = fields.Many2one("hjig.bop", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="bop_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    code = fields.Char(required=True)
    bop_line_id = fields.Many2one("hjig.bop.line", string="BOP Item", required=True, ondelete="cascade",
                                 domain="[('bop_id', '=', bop_id)]")
    is_exception = fields.Boolean(string="Approved Mapping-Pending Exception")
    exception_reason = fields.Text()
    exception_evidence = fields.Char()
    exception_accountable_designation = fields.Char()
    exception_due_date = fields.Date()
    exception_technical_approved = fields.Boolean()
    exception_ready = fields.Boolean(compute="_compute_readiness")
    topology = fields.Selection(
        [("single", "Single Component"), ("interface", "Interface Between Components")],
        required=True, default="single"
    )
    maturity = fields.Selection([("tentative", "Tentative"), ("confirmed", "Confirmed")],
                                required=True, default="tentative")
    quantity_per_assembly = fields.Float(required=True, default=1.0)
    interface_location = fields.Char()
    participant_ids = fields.One2many("hjig.bop.mapping.participant", "mapping_id", string="Participant Components")
    accountable_designation = fields.Char()
    due_date = fields.Date()
    evidence_reference = fields.Char()
    technical_confirmed = fields.Boolean()
    customer_signed = fields.Boolean(string="Customer Mapping Sign-off")
    customer_reference = fields.Char()
    is_confirmed_ready = fields.Boolean(compute="_compute_readiness")
    state = fields.Selection([("active", "Active"), ("reopened_via_ecn", "Reopened via ECN"),
                              ("superseded", "Superseded")], required=True, default="active", copy=False)
    changed_after_freeze = fields.Boolean(readonly=True, copy=False)
    change_reason = fields.Text(copy=False)
    ecn_required = fields.Selection([("yes", "Yes"), ("no", "No")], copy=False)
    ecn_reference = fields.Char(copy=False)

    _bop_mapping_unique = models.Constraint(
        "UNIQUE(bop_id, code)", "Mapping code must be unique within one BOP revision."
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("bop_id")._invalidate_design_release()
        return records

    @api.depends(
        "is_exception", "exception_reason", "exception_evidence",
        "exception_accountable_designation", "exception_due_date", "exception_technical_approved",
        "maturity", "participant_ids", "participant_ids.component_id", "topology",
        "technical_confirmed", "customer_signed", "customer_reference",
        "evidence_reference", "accountable_designation", "due_date",
    )
    def _compute_readiness(self):
        for mapping in self:
            mapping.exception_ready = bool(
                mapping.is_exception and mapping.exception_reason and mapping.exception_evidence
                and mapping.exception_accountable_designation and mapping.exception_due_date
                and mapping.exception_technical_approved
            )
            participant_count = len(mapping.participant_ids)
            topology_valid = (
                (mapping.topology == "single" and participant_count == 1)
                or (mapping.topology == "interface" and participant_count >= 2)
            )
            meeting_roles_valid = all(
                participant.role != "adjacent_meeting" or participant.component_id.is_meeting_component
                for participant in mapping.participant_ids
            )
            mapping.is_confirmed_ready = bool(
                not mapping.is_exception and mapping.maturity == "confirmed" and topology_valid
                and meeting_roles_valid and mapping.technical_confirmed and mapping.customer_signed
                and mapping.customer_reference and mapping.evidence_reference
                and mapping.accountable_designation and mapping.due_date
            )

    @api.constrains("topology", "participant_ids", "is_exception", "maturity")
    def _check_topology(self):
        for mapping in self.filtered(lambda record: not record.is_exception and record.maturity == "confirmed"):
            count = len(mapping.participant_ids)
            if mapping.topology == "single" and count != 1:
                raise ValidationError(_("Single Component topology requires exactly one participant."))
            if mapping.topology == "interface" and count < 2:
                raise ValidationError(_("Interface Between Components requires at least two participants."))

    def action_reopen_via_ecn(self):
        for mapping in self:
            if not mapping.change_reason or not mapping.ecn_reference:
                raise ValidationError(_("Enter change reason and ECN reference before reopening the mapping."))
            mapping.write({"state": "reopened_via_ecn", "changed_after_freeze": True,
                           "maturity": "tentative", "technical_confirmed": False,
                           "customer_signed": False})

    def write(self, vals):
        if self.filtered(lambda record: record.bop_id.state not in ("draft", "rejected")):
            raise ValidationError(_("Mappings are editable only while the BOP register is Draft or Rejected."))
        result = super().write(vals)
        self.mapped("bop_id")._invalidate_design_release()
        return result

    def unlink(self):
        bops = self.mapped("bop_id")
        result = super().unlink()
        bops._invalidate_design_release()
        return result


class HjigBopMappingParticipant(models.Model):
    _name = "hjig.bop.mapping.participant"
    _description = "BOP Interface Mapping Participant"
    _order = "mapping_id, sequence, id"

    sequence = fields.Integer(default=10)
    mapping_id = fields.Many2one("hjig.bop.mapping", required=True, ondelete="cascade", index=True)
    bop_id = fields.Many2one(related="mapping_id.bop_id", store=True, readonly=True, index=True)
    project_id = fields.Many2one(related="mapping_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    component_id = fields.Many2one("hjig.bop.product.component", required=True, ondelete="restrict",
                                  domain="[('bop_id', '=', bop_id)]")
    role = fields.Selection(
        [("primary_mount", "Primary Mount"), ("secondary_interface", "Secondary Interface"),
         ("adjacent_meeting", "Adjacent Meeting Component")], required=True, default="primary_mount"
    )
    quantity = fields.Float(required=True, default=1.0)
    position = fields.Char()

    @api.constrains("role", "component_id")
    def _check_meeting_role(self):
        for participant in self:
            if participant.role == "adjacent_meeting" and not participant.component_id.is_meeting_component:
                raise ValidationError(_("Adjacent Meeting Component role requires a component marked as Meeting / Interface Component."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("mapping_id.bop_id")._invalidate_design_release()
        return records

    def write(self, vals):
        if self.filtered(lambda record: record.mapping_id.bop_id.state not in ("draft", "rejected")):
            raise ValidationError(_("Mapping participants are editable only while the BOP register is Draft or Rejected."))
        result = super().write(vals)
        self.mapped("mapping_id.bop_id")._invalidate_design_release()
        return result

    def unlink(self):
        bops = self.mapped("mapping_id.bop_id")
        result = super().unlink()
        bops._invalidate_design_release()
        return result


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [("hjig.bop", "BOP")]
