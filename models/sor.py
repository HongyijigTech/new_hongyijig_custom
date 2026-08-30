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


AUTOMOTIVE_TEMPLATE_URL = "https://docs.google.com/document/d/1Q55pzs7BGJckDrM_PoNsg89O8rGfNGikgAY9Xbbxz1w/edit"
MED_CE_HA_TEMPLATE_URL = "https://docs.google.com/document/d/1e2CnHb2iRsk_PmiAmYYIDZXPBhph9j-jf-xCyhXMCwc/edit"


def _prompt(code, section, title, text, category="technical", phases=("design",), options=False, priority="normal"):
    return {
        "code": code, "section": section, "title": title, "text": text,
        "category": category, "phases": phases, "options": options or "",
        "priority": priority,
    }


# Guided intake prompts only: each answer becomes one governed SOR requirement.
# Downstream BOP, mould planning, risk, ECN and inspection forms remain separate.
AUTOMOTIVE_GUIDED_PROMPTS = [
    _prompt("AUTO-01.01", "1", "Programme Summary", "Project, vehicle model/variant, market and customer programme owner", "scope", ("concept",)),
    _prompt("AUTO-01.02", "1", "Programme Summary", "A/B/C-class surfaces, master sections, adjacent CAD and styling freeze status", "documentation", ("concept", "design"), "Yes / No for each item", "critical"),
    _prompt("AUTO-01.03", "1", "Programme Summary", "Programme milestones, target dates, owners and acceptance criteria", "scope", ("concept", "closure")),
    _prompt("AUTO-02.01", "2", "Part Description & Scope", "Part list: name, category, new/modified, visibility class and quantity per vehicle", "scope", ("concept", "design"), priority="critical"),
    _prompt("AUTO-02.02", "2", "Part Description & Scope", "Interfaces, adjacent parts, assembly sequence, known issues and assembly CAD", "technical", ("design", "prototype", "trial"), priority="critical"),
    _prompt("AUTO-02.03", "2", "Part Description & Scope", "Assembly method and required reference visuals", "technical", ("design", "prototype", "trial"), "Clips / Screws / Ultrasonic welding / Snap-fit / Adhesive / Other"),
    _prompt("AUTO-03.01", "3", "Material Specifications", "Material grade, supplier, colour, shrinkage and required TDS/SDS/restricted-substance evidence", "technical", ("design", "tooling", "trial"), priority="critical"),
    _prompt("AUTO-03.02", "3", "Material Specifications", "UV, heat, chemical and impact performance requirements", "quality", ("design", "prototype", "final_sample")),
    _prompt("AUTO-04.01", "4", "Engineering Requirements", "Wall thickness, draft angle, ISO tolerance and GD&T requirements", "technical", ("design", "tooling", "trial")),
    _prompt("AUTO-04.02", "4", "Engineering Requirements", "Temperature, UV, vibration and sealing/IP exposure conditions", "technical", ("design", "prototype", "final_sample")),
    _prompt("AUTO-05.01", "5", "Finish, Texture & Appearance", "Visibility class, texture supplier/depth/direction, paint, gloss and film thickness", "quality", ("design", "trial", "final_sample")),
    _prompt("AUTO-05.02", "5", "Finish, Texture & Appearance", "Viewing distance, lighting and defect rejection criteria", "quality", ("trial", "final_sample"), priority="critical"),
    _prompt("AUTO-06.01", "6", "DFM Requirements", "Required DFM deliverables and customer approval workflow", "documentation", ("design", "tooling"), priority="critical"),
    _prompt("AUTO-07.01", "7", "Tooling Requirements", "Tool class, production volume, steel, hardness, inserts, runner, cooling, ejection and shrinkage", "technical", ("design", "tooling", "trial"), priority="critical"),
    _prompt("AUTO-07.02", "7", "Tooling Requirements", "T0, T1 and T-Final trial locations, outputs and acceptance criteria", "quality", ("trial", "final_sample")),
    _prompt("AUTO-08.01", "8", "Validation Requirements", "Appearance, dimensional/CMM, GD&T, fitment, gap/flush and assembly-force validation", "quality", ("trial", "final_sample"), priority="critical"),
    _prompt("AUTO-08.02", "8", "Validation Requirements", "PPAP/ISIR level and required evidence", "documentation", ("final_sample", "shipment"), "PPAP Level 3 / Customer-specific / Not required"),
    _prompt("AUTO-09.01", "9", "Quality & Governance", "Applicable APQP stages, governance meetings and approval workflow", "responsibility", ("concept", "design", "tooling", "trial", "closure")),
    _prompt("AUTO-10.01", "10", "Risk Register Link", "Project-specific risks to be transferred to the existing Risk Register", "documentation", ("concept", "design", "tooling", "trial")),
    _prompt("AUTO-11.01", "11", "Packaging & Logistics", "Packing, pallet, labelling and logistics requirements", "logistics", ("shipment",)),
    _prompt("AUTO-12.01", "12", "Service & Governance Boundary", "Installation/corrective-action support scope and explicit no-product-warranty boundary", "commercial", ("concept", "installation", "closure"), priority="critical"),
    _prompt("AUTO-13.01", "13", "Required Attachments", "CAD, drawings, adjacent CAD, material data, colour/texture plaques, benchmarks, packaging and DFMEA attachments", "documentation", ("concept", "design")),
]


MED_CE_HA_GUIDED_PROMPTS = [
    _prompt("MCH-03.01", "3", "Benchmark Samples", "Benchmark samples for style/form, function, fitment, finish and other purposes", "documentation", ("concept", "design"), priority="critical"),
    _prompt("MCH-03.02", "3", "Benchmark Samples", "Sample return/retention policy, retention period and written declaration if no benchmark exists", "responsibility", ("concept", "closure")),
    _prompt("MCH-04.01", "4", "Part Scope & Product Description", "Tentative mould count and part-wise mould breakup; final lock occurs at TG-01", "scope", ("concept", "design"), priority="critical"),
    _prompt("MCH-04.02", "4", "Part Scope & Product Description", "Part list: name, category, new/modified, visibility class and assembly function", "scope", ("concept", "design"), priority="critical"),
    _prompt("MCH-05.01", "5", "Programme Milestones", "Target dates and customer/HJIG owners for the approved milestone chain", "scope", ("concept", "design", "prototype", "tooling", "trial", "final_sample")),
    _prompt("MCH-06.01", "6", "Engineering Responsibility", "Engineering responsibility option and, for Option C, the agreed HJIG engineering coordination scope", "responsibility", ("concept", "design"), "Option A — Customer / Option B — Customer-appointed third party / Option C — HJIG-coordinated scope", "critical"),
    _prompt("MCH-07.01", "7", "Style, Size & Weight Lock", "Overall product size, target weight/range and weight criticality", "technical", ("design", "prototype", "final_sample"), priority="critical"),
    _prompt("MCH-07.02", "7", "Style, Size & Weight Lock", "Visual approval method, surface finish, colour plaque, gloss, paint thickness, branding and texture reference", "quality", ("design", "trial", "final_sample"), priority="critical"),
    _prompt("MCH-08.01", "8", "BOP Readiness & Freeze", "Reference the existing BOP Lock Record and confirm every BOP has quantity, weight, datasheet, CAD and size status", "documentation", ("concept", "design"), priority="critical"),
    _prompt("MCH-08.02", "8", "BOP Readiness & Freeze", "BOP status: Frozen, Envelope Only or Pending; Pending places engineering on HOLD", "technical", ("concept", "design", "prototype"), "Frozen / Envelope Only / Pending", "critical"),
    _prompt("MCH-09.01", "9", "Assembly, Serviceability & Fitment", "Assembly method, sealing/IP, insert/over-moulding, adjacent parts and functional interfaces", "technical", ("design", "prototype", "trial"), priority="critical"),
    _prompt("MCH-09.02", "9", "Assembly, Serviceability & Fitment", "End-user/technician serviceability, accessible components, opening method and service cycles", "technical", ("design", "prototype", "final_sample")),
    _prompt("MCH-09.03", "9", "Assembly, Serviceability & Fitment", "Gate/runner/parting/ejector mark location and visibility acceptance", "quality", ("design", "tooling", "trial"), priority="critical"),
    _prompt("MCH-09.04", "9", "Assembly, Serviceability & Fitment", "Step-by-step assembly sequence and involved BOP/parts", "technical", ("design", "prototype", "trial")),
    _prompt("MCH-09.05", "9", "Assembly, Serviceability & Fitment", "Gap/flush, play, snap retention force and fitment criteria", "quality", ("prototype", "trial", "final_sample")),
    _prompt("MCH-10.01", "10", "Material Specification", "Plastic material, alternate material, colour, shrinkage and HJIG recommendation requirement", "technical", ("design", "tooling", "trial"), priority="critical"),
    _prompt("MCH-10.02", "10", "Material Specification", "UV, heat, chemical, flame, food-contact, RoHS and biodegradable requirements", "quality", ("design", "prototype", "final_sample")),
    _prompt("MCH-11.01", "11", "Environmental Exposure", "Operating/storage temperature, humidity, UV, vibration, chemicals, altitude and pressure", "technical", ("design", "prototype", "final_sample")),
    _prompt("MCH-11.02", "11", "Environmental Exposure", "Body contact, sterilisation and drop/impact exposure", "quality", ("design", "prototype", "final_sample")),
    _prompt("MCH-12.01", "12", "Appearance Inspection", "Viewing distance, lighting, golden sample and defect acceptance criteria", "quality", ("trial", "final_sample"), priority="critical"),
    _prompt("MCH-13.01", "13", "Dimensional & First Article", "Tolerance standard, GD&T, critical dimensions and non-critical variance", "quality", ("design", "trial", "final_sample"), priority="critical"),
    _prompt("MCH-13.02", "13", "Dimensional & First Article", "FAI/ISIR and CMM scope, standard, approver and completion gate", "documentation", ("trial", "final_sample", "shipment")),
    _prompt("MCH-14.01", "14", "DFM Requirements", "Required Moldflow, warpage, sink, gate, parting/slide, draft, cooling and ejection deliverables", "documentation", ("design", "tooling"), priority="critical"),
    _prompt("MCH-15.01", "15", "Functional Testing", "Product function, T0/T1/T-Final test method, conditions and acceptance basis", "quality", ("prototype", "trial", "final_sample"), priority="critical"),
    _prompt("MCH-15.02", "15", "Functional Testing", "Physical prototype and CAE requirement plus written prototype approval", "documentation", ("prototype", "tooling")),
    _prompt("MCH-16.01", "16", "Moulding Machine Assumptions", "Machine ownership/outsourcing, tonnage, shot capacity, tie bars, clamp and ejection", "technical", ("design", "tooling"), priority="critical"),
    _prompt("MCH-16.02", "16", "Moulding Machine Assumptions", "Automation, hot-runner controller, maximum injection pressure and cycle-time assumption", "technical", ("design", "tooling", "trial")),
    _prompt("MCH-17.01", "17", "Regulatory & Certification WBS", "Applicable certifications, responsibility and required WBS", "responsibility", ("concept", "design", "final_sample"), "BIS/IS / CE / FDA / IEC 60601 / IP / EMI-EMC / RoHS-WEEE / UL-ETL / Energy Star / Other", "critical"),
    _prompt("MCH-18.01", "18", "Domain-Specific Requirements", "Medical, Home Appliance or Consumer Electronics domain-specific declarations", "technical", ("concept", "design", "prototype", "final_sample"), priority="critical"),
    _prompt("MCH-19.01", "19", "Tooling Requirements", "Annual volume, tool life, tool class/steel, runner type and delivery model", "technical", ("design", "tooling", "shipment")),
    _prompt("MCH-20.01", "20", "Trials, Samples & Validation", "T0/T1/T-Final location, acceptance criteria, sample quantity and additional-trial boundary", "quality", ("trial", "final_sample"), priority="critical"),
    _prompt("MCH-21.01", "21", "Change Management", "Customer acceptance that any post-lock change is a formal ECN with cost/timeline/trial impact", "commercial", ("design", "tooling", "trial", "final_sample"), priority="critical"),
    _prompt("MCH-22.01", "22", "Packaging & Logistics", "Packing, bagging, label, pallet, origin and handling requirements", "logistics", ("shipment",)),
    _prompt("MCH-23.01", "23", "Governance Boundary", "No HJIG product/tool warranty; record only governance and contracted installation/corrective-action support", "commercial", ("concept", "installation", "closure"), priority="critical"),
    _prompt("MCH-24.01", "24", "Responsibility Boundaries", "Customer acceptance of the HJIG/customer responsibility matrix", "responsibility", ("concept", "closure"), priority="critical"),
    _prompt("MCH-25.01", "25", "Customer Declaration & Sign-Off", "Customer declaration and authorised sign-off of the complete frozen SOR", "documentation", ("concept",), priority="critical"),
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
    guided_template_code = fields.Char(readonly=True, copy=False, tracking=True)
    guided_template_url = fields.Char(readonly=True, copy=False)
    order_punch_confirmed = fields.Boolean(
        string="Approved Order Punch Confirmed",
        tracking=True,
        help="The MED/CE/HA guided SOR may be issued only after the approved order is punched.",
    )
    engineering_responsibility = fields.Selection(
        [
            ("customer", "Option A — Engineering by Customer"),
            ("third_party", "Option B — Customer-appointed Third Party"),
            ("hjig_coordinated", "Option C — HJIG-coordinated Agreed Scope"),
        ],
        tracking=True,
    )
    engineering_scope = fields.Text(string="Option C Engineering Scope", tracking=True)
    customer_signoff_name = fields.Char(tracking=True)
    customer_signoff_designation = fields.Char(tracking=True)
    customer_signoff_date = fields.Date(tracking=True)
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
        "effective_date", "installation_support_scope", "notes", "guided_template_code",
        "guided_template_url", "order_punch_confirmed", "engineering_responsibility",
        "engineering_scope", "customer_signoff_name", "customer_signoff_designation",
        "customer_signoff_date",
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

    def action_load_approved_template(self):
        """Load controlled prompts while retaining the existing downstream forms."""
        requirement_model = self.env["hjig.sor.requirement"]
        verification_model = self.env["hjig.sor.requirement.verification"]
        for sor in self:
            if sor.intake_route != "hongyi_guided":
                raise UserError(_("Template loading is only for Route B — Hongyi guided SORs."))
            if sor.state not in ("draft", "mapping"):
                raise UserError(_("The approved template can only be loaded in Draft or Mapping state."))
            if sor.requirement_ids:
                raise UserError(_("Requirements already exist. Continue mapping the existing rows."))
            if sor.industry != "automotive" and not sor.order_punch_confirmed:
                raise ValidationError(_("Confirm the approved Order Punch before issuing the MED/CE/HA SOR."))

            if sor.industry == "automotive":
                prompts = AUTOMOTIVE_GUIDED_PROMPTS
                template_code = "HONGYI-MASTER-AUTOMOTIVE-SOR"
                template_url = AUTOMOTIVE_TEMPLATE_URL
            else:
                prompts = MED_CE_HA_GUIDED_PROMPTS
                template_code = "SOR-MED-CE-HA-v2.1"
                template_url = MED_CE_HA_TEMPLATE_URL

            domain_labels = {
                "medical": "Medical Devices",
                "home_appliances": "Home Appliances",
                "consumer_electronics": "Consumer Electronics",
            }
            for sequence, prompt in enumerate(prompts, 1):
                prompt_text = prompt["text"]
                if prompt["code"] == "MCH-18.01":
                    prompt_text = "%s — %s" % (domain_labels[sor.industry], prompt_text)
                requirement = requirement_model.create({
                    "sor_id": sor.id,
                    "sequence": sequence * 10,
                    "requirement_id": prompt["code"],
                    "template_key": prompt["code"],
                    "section_code": prompt["section"],
                    "section_title": prompt["title"],
                    "category": prompt["category"],
                    "requirement_text": prompt_text,
                    "response_options": prompt["options"],
                    "declaration_state": "pending",
                    "source_reference": "Section %s" % prompt["section"],
                    "priority": prompt["priority"],
                    "owner_id": sor.owner_id.id,
                    "clarification_due_date": sor.effective_date or fields.Date.context_today(sor),
                })
                for phase in prompt["phases"]:
                    verification_model.create({
                        "requirement_id": requirement.id,
                        "phase": phase,
                        "check_required": True,
                        "verification_method": "Review the frozen SOR declaration against accepted evidence.",
                        "required_evidence": "Accepted evidence for %s at %s" % (prompt["code"], phase),
                        "responsible_designation_id": sor.approval_authority_designation_id.id,
                    })
            sor.write({"guided_template_code": template_code, "guided_template_url": template_url})
        return True

    def _check_ready_for_review(self):
        for sor in self:
            if not sor.requirement_ids:
                raise ValidationError(_("At least one SOR requirement is required."))
            if not sor.effective_date:
                raise ValidationError(_("Effective Date is required before SOR review."))
            if sor.guided_template_code and not (
                (sor.customer_signoff_name or "").strip()
                and (sor.customer_signoff_designation or "").strip()
                and sor.customer_signoff_date
            ):
                raise ValidationError(_("Customer sign-off name, designation and date are required before guided SOR review."))
            if sor.industry != "automotive":
                if not sor.order_punch_confirmed:
                    raise ValidationError(_("The approved Order Punch must be confirmed before SOR review."))
                if not sor.engineering_responsibility:
                    raise ValidationError(_("Engineering responsibility Option A, B or C is required."))
                if sor.engineering_responsibility == "hjig_coordinated" and not (sor.engineering_scope or "").strip():
                    raise ValidationError(_("Option C requires the agreed HJIG engineering coordination scope."))
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
    template_key = fields.Char(readonly=True, copy=False, index=True)
    section_code = fields.Char(index=True, tracking=True)
    section_title = fields.Char(tracking=True)
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
    original_customer_wording = fields.Text(
        string="Original Customer Wording",
        tracking=True,
        help="Verbatim customer wording or questionnaire response. Keep this separate from the governed Hongyi interpretation.",
    )
    interpretation_confidence = fields.Integer(
        string="Interpretation Confidence %",
        tracking=True,
        help="Optional review aid only. It never replaces human review or approval.",
    )
    confirmation_party = fields.Selection(
        [
            ("hongyi", "Hongyi Technical / PMO"),
            ("customer", "Customer Technical"),
            ("joint", "Joint Confirmation"),
        ],
        tracking=True,
    )
    critical_review = fields.Boolean(string="Critical Review Required", tracking=True)
    conflict_detected = fields.Boolean(string="Conflict Detected", tracking=True)
    review_flag = fields.Text(string="Review Flag / Reason", tracking=True)
    clarification_question = fields.Text(tracking=True)
    conflict_resolution = fields.Text(
        help="Required before a conflicting requirement can be submitted for SOR freeze.",
        tracking=True,
    )
    response_options = fields.Text(readonly=True)
    customer_declaration = fields.Text(tracking=True)
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

    @api.constrains("interpretation_confidence")
    def _check_interpretation_confidence(self):
        for requirement in self:
            if requirement.interpretation_confidence < 0 or requirement.interpretation_confidence > 100:
                raise ValidationError(_("Interpretation Confidence must be between 0 and 100 percent."))

    @api.model_create_multi
    def create(self, vals_list):
        if any(not vals.get("declaration_state") for vals in vals_list):
            raise ValidationError(_("Declaration State is required; blank is not allowed."))
        return super().create(vals_list)

    @api.constrains("sor_id")
    def _check_sor_not_frozen(self):
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise ValidationError(_("Requirements cannot be added after SOR review begins."))

    def write(self, vals):
        if "declaration_state" in vals and not vals["declaration_state"]:
            raise ValidationError(_("Declaration State is required; blank is not allowed."))
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise ValidationError(_("Requirements are read-only after SOR review begins."))
        return super().write(vals)

    def unlink(self):
        if any(requirement.sor_id.state in ("review", "frozen", "superseded") for requirement in self):
            raise UserError(_("Requirements cannot be deleted after SOR review begins."))
        return super().unlink()

    def _check_review_readiness(self):
        self.ensure_one()
        if self.declaration_state in ("unknown_recommendation", "pending"):
            raise ValidationError(
                _("Requirement %s still has an unresolved recommendation or customer clarification.")
                % self.requirement_id
            )
        if self.declaration_state == "specified":
            if self.template_key and not (self.customer_declaration or "").strip():
                raise ValidationError(_("Template requirement %s needs the customer's declaration.") % self.requirement_id)
            if not (self.acceptance_criteria or "").strip():
                raise ValidationError(_("Specified requirement %s needs acceptance criteria.") % self.requirement_id)
            if not self.verification_ids.filtered("check_required"):
                raise ValidationError(_("Specified requirement %s must be allocated to at least one phase.") % self.requirement_id)
            if (self.critical_review or self.conflict_detected) and not self.confirmation_party:
                raise ValidationError(
                    _("Critical or conflicting requirement %s needs a confirmation party.") % self.requirement_id
                )
            if self.conflict_detected and not (self.conflict_resolution or "").strip():
                raise ValidationError(
                    _("Conflicting requirement %s needs a documented resolution before freeze.") % self.requirement_id
                )
        if self.sor_id.intake_route == "customer_sor" and not (self.source_reference or "").strip():
            raise ValidationError(_("Route A requirement %s needs its customer source clause/page.") % self.requirement_id)
        if self.declaration_state in ("unknown_recommendation", "pending"):
            if not self.owner_id or not self.clarification_due_date or not (self.clarification_question or "").strip():
                raise ValidationError(
                    _("Open requirement %s needs an owner, clarification question, and due date.") % self.requirement_id
                )


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
