import hashlib
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


FORM_TYPES = [
    ("programme_builder", "Programme Builder"),
    ("portfolio_guard", "PortfolioGuard"),
]
FORM_TYPE_FROM_PAYLOAD = {
    "PROGRAMME_BUILDER": "programme_builder",
    "PORTFOLIOGUARD": "portfolio_guard",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
VALID_STAGES = {
    "Concept", "Product Design", "Engineering", "Supplier Selection", "Pre-Tooling",
    "Tooling", "Trial", "Buyoff", "Shipment", "Installation",
}
VALID_CATEGORIES = {
    "Appliance", "Consumer Product", "Industrial", "Automotive", "Air Cooler", "Medical",
    "Aerospace", "Other",
}
VALID_START_WINDOWS = {
    "Already Active", "Within 30 Days", "Within 1–3 Months", "After 3 Months", "Not Decided",
}
VALID_TOOLING_STATUSES = {"Exact", "Approximate", "Not Known Yet"}
VALID_ENGAGEMENT_MODELS = {
    "PROGRAMME_GOVERNANCE", "ADVISORY_TOOLLOCK_LITE", "SOURCEBRIDGE_ONLY", "NOT_SURE",
}


class HjigSSeriesIntakeSubmission(models.Model):
    _name = "hjig.sseries.intake.submission"
    _description = "Immutable S-Series Website Submission"
    _order = "received_at desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    client_submission_id = fields.Char(required=True, readonly=True, copy=False, index=True)
    form_type = fields.Selection(FORM_TYPES, required=True, readonly=True, copy=False, index=True)
    frontend_spec_version = fields.Char(required=True, readonly=True, copy=False)
    submitted_at_client = fields.Char(readonly=True, copy=False)
    received_at = fields.Datetime(required=True, readonly=True, copy=False, default=fields.Datetime.now)
    payload_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    signature_timestamp = fields.Char(readonly=True, copy=False)
    raw_payload_json = fields.Json(
        required=True,
        readonly=True,
        copy=False,
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )
    consent_given = fields.Boolean(required=True, readonly=True, copy=False)
    company_name = fields.Char(required=True, readonly=True, copy=False, index=True)
    contact_name = fields.Char(required=True, readonly=True, copy=False)
    customer_email = fields.Char(required=True, readonly=True, copy=False, index=True)
    customer_mobile = fields.Char(readonly=True, copy=False)
    customer_country = fields.Char(readonly=True, copy=False)
    project_ids = fields.One2many("hjig.sseries.intake.project", "submission_id", readonly=True)
    case_ids = fields.One2many("hjig.sseries.case", "submission_id", readonly=True)
    attachment_gateway_ids = fields.One2many(
        "hjig.sseries.intake.attachment.gateway", "submission_id", readonly=True
    )
    project_count = fields.Integer(compute="_compute_counts")
    case_count = fields.Integer(compute="_compute_counts")
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, copy=False, default=lambda self: self.env.company
    )

    _client_submission_unique = models.Constraint(
        "UNIQUE(client_submission_id)",
        "Client submission ID must be unique.",
    )

    @api.depends("project_ids", "case_ids")
    def _compute_counts(self):
        for record in self:
            record.project_count = len(record.project_ids)
            record.case_count = len(record.case_ids)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hjig_sseries_ingest"):
            raise UserError(_("Website submission snapshots may be created only through the governed intake service."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("A received S-Series website submission is immutable."))

    def unlink(self):
        raise UserError(_("A received S-Series website submission cannot be deleted."))

    @api.model
    def _canonical_payload(self, payload):
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @api.model
    def _supported_versions(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "hjig.sseries.supported_frontend_specs",
            "ProgrammeBuilder-V2,PortfolioGuard-v1.7",
        )
        return {item.strip() for item in raw.split(",") if item.strip()}

    @api.model
    def _reject_odoo_identifiers(self, value, path="payload"):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower().startswith("odoo_"):
                    raise ValidationError(_("Public intake must not contain Odoo identifiers (%s).") % f"{path}.{key}")
                self._reject_odoo_identifiers(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self._reject_odoo_identifiers(child, f"{path}[{index}]")

    @api.model
    def _safe_identifier(self, value, label, prefix=None):
        if not isinstance(value, str) or not (3 <= len(value) <= 120) or not SAFE_ID_RE.fullmatch(value):
            raise ValidationError(_("%s is invalid.") % label)
        if prefix and not value.startswith(prefix):
            raise ValidationError(_("%s must start with %s.") % (label, prefix))
        return value

    @api.model
    def _required_text(self, value, label, limit=500):
        text = str(value or "").strip()
        if not text:
            raise ValidationError(_("%s is required.") % label)
        if len(text) > limit:
            raise ValidationError(_("%s is too long.") % label)
        return text

    @api.model
    def _nonnegative_integer(self, value, label, allow_blank=True):
        if value in (None, "") and allow_blank:
            return 0
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValidationError(_("%s must be a non-negative whole number.") % label)
        return value

    @api.model
    def _nonnegative_number(self, value, label, allow_blank=True):
        if value in (None, "") and allow_blank:
            return 0.0
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValidationError(_("%s cannot be negative or non-numeric.") % label)
        return value

    @api.model
    def _normalise_component_values(self, project, component, index):
        return {
            "project_id": project.id,
            "sequence": index * 10,
            "component_index": index,
            "name": self._required_text(component.get("component_name"), _("Component name"), 300),
            "component_type": str(component.get("component_type") or component.get("component_type_selection") or ""),
            "component_function": self._required_text(
                component.get("component_function"), _("Component function"), 2000
            ),
            "preferred_solution_route": self._required_text(
                component.get("preferred_solution_route"), _("Preferred solution route"), 500
            ),
            "material_grade": str(component.get("material_grade") or ""),
            "technical_specification_status": str(component.get("technical_specification_status") or ""),
            "expected_year_1_quantity": self._nonnegative_integer(
                component.get("expected_year_1_quantity"), _("Expected Year-1 quantity")
            ),
            "target_unit_price": self._nonnegative_number(
                component.get("target_unit_price"), _("Target unit price")
            ),
            "raw_component_json": component,
        }

    @api.model
    def _sourcebridge_details(self, project_payload):
        services = project_payload.get("services") or {}
        selected = bool(
            project_payload.get("sourcebridge_selected")
            or project_payload.get("sourcing_activity_selected")
            or services.get("overseas_sourcing_supplier_development")
            or project_payload.get("engagement_model") == "SOURCEBRIDGE_ONLY"
            or project_payload.get("primary_engagement_route") == "Sourcing-led / SourceBridge only"
        )
        details = project_payload.get("sourcebridge_details") or {}
        if not selected:
            return False, {}, []
        project_level = details.get("project_level") or {}
        self._required_text(project_level.get("sourcing_objective"), _("SourceBridge sourcing objective"), 3000)
        components = details.get("components")
        package_count = project_level.get("sourcing_package_count")
        if not isinstance(package_count, int) or isinstance(package_count, bool) or package_count < 1:
            raise ValidationError(_("SourceBridge sourcing package count must be a positive whole number."))
        if not isinstance(components, list) or len(components) != package_count:
            raise ValidationError(_("SourceBridge component count must match the sourcing package count."))
        return True, project_level, components

    @api.model
    def _project_values(self, submission, payload, sequence, client_project_id):
        project_name = self._required_text(payload.get("project_name"), _("Project name"), 300)
        selected, sourcebridge_level, components = self._sourcebridge_details(payload)
        services = payload.get("services") or {}
        if services and not isinstance(services, dict):
            raise ValidationError(_("Services must be an object."))
        current_stage = self._required_text(
            payload.get("current_project_stage"), _("Current project stage"), 120
        )
        if current_stage not in VALID_STAGES:
            raise ValidationError(_("Current project stage is not supported."))
        category = self._required_text(
            payload.get("product_category") or payload.get("customer_stated_product_category"),
            _("Product category"),
            120,
        )
        if category not in VALID_CATEGORIES:
            raise ValidationError(_("Product category is not supported."))
        expected_start_window = str(payload.get("expected_start_window") or "")
        if submission.form_type == "portfolio_guard" and expected_start_window not in VALID_START_WINDOWS:
            raise ValidationError(_("Expected start window is not supported."))
        tooling_status = self._required_text(
            payload.get("tooling_value_status"), _("Tooling value status"), 120
        )
        if tooling_status not in VALID_TOOLING_STATUSES:
            raise ValidationError(_("Tooling value status is not supported."))
        engagement_model = str(payload.get("engagement_model") or "")
        if engagement_model and engagement_model not in VALID_ENGAGEMENT_MODELS:
            raise ValidationError(_("Engagement model is not supported."))
        duration = payload.get("duration_months")
        if duration is None:
            duration = payload.get("customer_expected_duration_months")
        duration_range = str(payload.get("customer_expected_duration_range") or "")
        if duration in (None, ""):
            if submission.form_type == "portfolio_guard":
                # PortfolioGuard's governed customer form does not require a
                # project-duration estimate. Preserve unknown as zero so that
                # internal review can establish it without inventing a value.
                duration = 0
            elif not duration_range:
                raise ValidationError(_("Expected duration is required."))
            else:
                duration = 0
        elif not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise ValidationError(_("Expected duration must be a positive whole number of months."))
        mould_count = payload.get("mould_count")
        if mould_count is None:
            mould_count = payload.get("customer_stated_mould_count")
        major_component_count = payload.get("major_components")
        if major_component_count is None:
            major_component_count = payload.get("customer_stated_major_components")
        tooling_value = payload.get("tooling_project_value")
        if tooling_value is None:
            tooling_value = payload.get("customer_stated_tooling_project_value")
        tooling_value = self._nonnegative_number(tooling_value, _("Customer-stated tooling value"))
        if tooling_status != "Not Known Yet" and tooling_value <= 0:
            raise ValidationError(_("Customer-stated tooling value must be positive unless it is not known yet."))
        return {
            "submission_id": submission.id,
            "client_project_id": client_project_id,
            "sequence": sequence,
            "name": project_name,
            "current_project_stage": current_stage,
            "expected_start_window": expected_start_window,
            "product_category": category,
            "expected_duration_months": duration,
            "expected_duration_range": duration_range,
            "mould_count": self._nonnegative_integer(mould_count, _("Mould count")),
            "major_component_count": self._nonnegative_integer(
                major_component_count, _("Major component count")
            ),
            "tooling_value_status": tooling_status,
            "customer_stated_tooling_value": tooling_value,
            "engagement_model": engagement_model,
            "services_json": services,
            "existing_commercial_json": payload.get("existing_hongyi_commercial") or {},
            "business_at_stake_json": payload.get("business_at_stake") or {},
            "sourcebridge_selected": selected,
            "sourcebridge_objective": str(sourcebridge_level.get("sourcing_objective") or ""),
            "sourcebridge_package_count": len(components),
            "raw_project_json": payload,
        }, components

    @api.model
    def ingest_payload(self, payload, signature_timestamp=None):
        if not isinstance(payload, dict):
            raise ValidationError(_("JSON payload must be an object."))
        self._reject_odoo_identifiers(payload)

        payload_form_type = payload.get("form_type")
        form_type = FORM_TYPE_FROM_PAYLOAD.get(payload_form_type)
        if not form_type:
            raise ValidationError(_("Unsupported or missing form_type."))
        client_submission_id = self._safe_identifier(
            payload.get("client_submission_id"),
            _("Client submission ID"),
            "PB-" if form_type == "programme_builder" else "PG-",
        )
        frontend_spec = self._required_text(
            payload.get("frontend_spec_version"), _("Frontend spec version"), 120
        )
        if frontend_spec not in self._supported_versions():
            raise ValidationError(_("Frontend spec version is not enabled in Odoo."))
        if payload.get("consent_given") is not True:
            raise ValidationError(_("Customer consent is required."))

        canonical = self._canonical_payload(payload)
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        existing = self.search([("client_submission_id", "=", client_submission_id)], limit=1)
        if existing:
            if existing.payload_hash != payload_hash:
                raise ValidationError(
                    _("Conflicting payload received for an existing client submission ID; manual review is required.")
                )
            return {"submission": existing, "idempotent": True}

        if form_type == "programme_builder":
            customer = payload
            project_payloads = [(client_submission_id, payload)]
        else:
            customer = payload.get("customer") or {}
            portfolio = payload.get("portfolio") or {}
            project_payloads_raw = payload.get("projects")
            if not isinstance(project_payloads_raw, list) or not project_payloads_raw:
                raise ValidationError(_("PortfolioGuard requires at least one project."))
            if len(project_payloads_raw) > 100:
                raise ValidationError(_("PortfolioGuard cannot contain more than 100 project blocks."))
            defined_count = portfolio.get("projects_defined_count")
            if defined_count is not None and defined_count != len(project_payloads_raw):
                raise ValidationError(_("PortfolioGuard project count does not match projects_defined_count."))
            project_payloads = []
            seen = set()
            for item in project_payloads_raw:
                if not isinstance(item, dict):
                    raise ValidationError(_("Each PortfolioGuard project must be an object."))
                client_project_id = self._safe_identifier(
                    item.get("client_project_id"), _("Client project ID")
                )
                if client_project_id in seen:
                    raise ValidationError(_("PortfolioGuard contains a duplicate client project ID."))
                seen.add(client_project_id)
                project_payloads.append((client_project_id, item))
            total_expected = portfolio.get("total_projects_expected")
            if total_expected is not None:
                total_expected = self._nonnegative_integer(
                    total_expected, _("Total projects expected"), allow_blank=False
                )
                if total_expected < len(project_payloads):
                    raise ValidationError(_("Submitted projects exceed total projects expected."))
            concurrent = portfolio.get("customer_maximum_concurrent_projects")
            if concurrent is not None:
                concurrent = self._nonnegative_integer(
                    concurrent, _("Maximum concurrent projects"), allow_blank=False
                )
                if concurrent < 1 or (total_expected is not None and concurrent > total_expected):
                    raise ValidationError(_("Maximum concurrent projects is inconsistent."))

        company_name = self._required_text(customer.get("company_name"), _("Company name"), 300)
        contact_name = self._required_text(
            customer.get("customer_contact_name") or customer.get("contact_person"),
            _("Customer contact name"),
            300,
        )
        email = self._required_text(
            customer.get("customer_email") or customer.get("email"), _("Customer email"), 320
        ).lower()
        if not EMAIL_RE.fullmatch(email):
            raise ValidationError(_("Customer email is invalid."))

        ingest_context = dict(self.env.context, hjig_sseries_ingest=True)
        submission = self.with_context(ingest_context).create({
            "name": self.env["ir.sequence"].next_by_code("hjig.sseries.intake.submission") or "New",
            "client_submission_id": client_submission_id,
            "form_type": form_type,
            "frontend_spec_version": frontend_spec,
            "submitted_at_client": str(payload.get("submitted_at") or ""),
            "payload_hash": payload_hash,
            "signature_timestamp": str(signature_timestamp or ""),
            "raw_payload_json": payload,
            "consent_given": True,
            "company_name": company_name,
            "contact_name": contact_name,
            "customer_email": email,
            "customer_mobile": str(customer.get("customer_mobile") or ""),
            "customer_country": str(customer.get("customer_country") or ""),
            "company_id": self.env.company.id,
        })

        Project = self.env["hjig.sseries.intake.project"].with_context(ingest_context)
        Component = self.env["hjig.sseries.intake.component"].with_context(ingest_context)
        Case = self.env["hjig.sseries.case"].with_context(ingest_context)
        for index, (client_project_id, project_payload) in enumerate(project_payloads, 1):
            project_vals, components = self._project_values(
                submission, project_payload, index * 10, client_project_id
            )
            project = Project.create(project_vals)
            for component_index, component in enumerate(components, 1):
                component_record = Component.create(
                    self._normalise_component_values(project, component, component_index)
                )
                self.env["hjig.sseries.intake.attachment.gateway"].claim_component_attachments(
                    component_record, component
                )
            Case.create({
                "name": self.env["ir.sequence"].next_by_code("hjig.sseries.case") or "New",
                "submission_id": submission.id,
                "intake_project_id": project.id,
                "company_id": self.env.company.id,
                "customer_name": company_name,
                "project_name": project.name,
                "stage": "s0_received",
                "next_action": _("Assign owner and start internal review"),
            })
        return {"submission": submission, "idempotent": False}


class HjigSSeriesIntakeProject(models.Model):
    _name = "hjig.sseries.intake.project"
    _description = "Immutable S-Series Intake Project Snapshot"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one(
        "hjig.sseries.intake.submission", required=True, readonly=True, ondelete="restrict", index=True
    )
    client_project_id = fields.Char(required=True, readonly=True, copy=False, index=True)
    sequence = fields.Integer(required=True, readonly=True)
    name = fields.Char(required=True, readonly=True, index=True)
    current_project_stage = fields.Char(readonly=True)
    expected_start_window = fields.Char(readonly=True)
    product_category = fields.Char(readonly=True)
    expected_duration_months = fields.Integer(readonly=True)
    expected_duration_range = fields.Char(readonly=True)
    mould_count = fields.Integer(readonly=True)
    major_component_count = fields.Integer(readonly=True)
    tooling_value_status = fields.Char(readonly=True)
    customer_stated_tooling_value = fields.Float(readonly=True)
    engagement_model = fields.Char(readonly=True)
    services_json = fields.Json(readonly=True)
    existing_commercial_json = fields.Json(
        readonly=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    business_at_stake_json = fields.Json(
        readonly=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    sourcebridge_selected = fields.Boolean(readonly=True, index=True)
    sourcebridge_objective = fields.Text(readonly=True)
    sourcebridge_package_count = fields.Integer(readonly=True)
    component_ids = fields.One2many("hjig.sseries.intake.component", "project_id", readonly=True)
    raw_project_json = fields.Json(
        required=True,
        readonly=True,
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )
    case_id = fields.One2many("hjig.sseries.case", "intake_project_id", readonly=True)

    _submission_project_unique = models.Constraint(
        "UNIQUE(submission_id, client_project_id)",
        "Client project ID must be unique within a submission.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hjig_sseries_ingest"):
            raise UserError(_("Intake project snapshots may be created only through the governed intake service."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("An S-Series intake project snapshot is immutable."))

    def unlink(self):
        raise UserError(_("An S-Series intake project snapshot cannot be deleted."))


class HjigSSeriesIntakeComponent(models.Model):
    _name = "hjig.sseries.intake.component"
    _description = "Immutable SourceBridge Intake Component Snapshot"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "hjig.sseries.intake.project", required=True, readonly=True, ondelete="restrict", index=True
    )
    sequence = fields.Integer(required=True, readonly=True)
    component_index = fields.Integer(required=True, readonly=True)
    name = fields.Char(required=True, readonly=True)
    component_type = fields.Char(readonly=True)
    component_function = fields.Text(required=True, readonly=True)
    preferred_solution_route = fields.Char(required=True, readonly=True)
    material_grade = fields.Char(readonly=True)
    technical_specification_status = fields.Char(readonly=True)
    expected_year_1_quantity = fields.Integer(readonly=True)
    target_unit_price = fields.Float(
        readonly=True, groups="new_hongyijig_custom.group_hjig_sseries_manager"
    )
    raw_component_json = fields.Json(
        required=True,
        readonly=True,
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )
    reference_image_attachment_id = fields.Many2one(
        "ir.attachment",
        readonly=True,
        copy=False,
        ondelete="restrict",
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )
    technical_file_attachment_id = fields.Many2one(
        "ir.attachment",
        readonly=True,
        copy=False,
        ondelete="restrict",
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )

    _project_component_unique = models.Constraint(
        "UNIQUE(project_id, component_index)",
        "Component index must be unique within an intake project.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hjig_sseries_ingest"):
            raise UserError(_("Intake component snapshots may be created only through the governed intake service."))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("hjig_sseries_attachment_bind") and set(vals) <= {
            "reference_image_attachment_id", "technical_file_attachment_id"
        }:
            return super().write(vals)
        raise UserError(_("A SourceBridge intake component snapshot is immutable."))

    def unlink(self):
        raise UserError(_("A SourceBridge intake component snapshot cannot be deleted."))


class HjigSSeriesCase(models.Model):
    _name = "hjig.sseries.case"
    _description = "S-Series Employee Cockpit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, create_date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    submission_id = fields.Many2one(
        "hjig.sseries.intake.submission", required=True, readonly=True, ondelete="restrict", index=True
    )
    intake_project_id = fields.Many2one(
        "hjig.sseries.intake.project", required=True, readonly=True, ondelete="restrict", index=True
    )
    form_type = fields.Selection(related="submission_id.form_type", store=True, readonly=True)
    client_submission_id = fields.Char(related="submission_id.client_submission_id", store=True, readonly=True)
    client_project_id = fields.Char(related="intake_project_id.client_project_id", store=True, readonly=True)
    customer_name = fields.Char(required=True, readonly=True, index=True)
    project_name = fields.Char(required=True, readonly=True, index=True)
    stage = fields.Selection(
        [
            ("s0_received", "S0 Submission Record"),
            ("s1_review", "S1 Internal Review"),
            ("s2_assessment", "S2 Governance Assessment"),
            ("s3_proposal", "S3 Commercial Proposal"),
            ("s4_activation", "S4 Activation Pack"),
            ("s5_sourcing", "S5 Sourcing Pack"),
            ("s6_handover", "S6 Team Handover"),
            ("b0_released", "Released to B0"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="s0_received",
        tracking=True,
        index=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent")], default="0", tracking=True
    )
    owner_id = fields.Many2one("res.users", tracking=True, domain="[('share', '=', False)]")
    reviewer_id = fields.Many2one("res.users", tracking=True, domain="[('share', '=', False)]")
    next_action = fields.Char(readonly=True, tracking=True)
    blocker_summary = fields.Text(readonly=True, tracking=True)
    exception_state = fields.Selection(
        [("clear", "Clear"), ("attention", "Needs Attention"), ("blocked", "Blocked")],
        default="clear",
        required=True,
        tracking=True,
    )
    sourcebridge_required = fields.Boolean(related="intake_project_id.sourcebridge_selected", readonly=True)
    partner_id = fields.Many2one("res.partner", ondelete="restrict", tracking=True)
    lead_id = fields.Many2one("crm.lead", ondelete="restrict", tracking=True)
    sale_order_id = fields.Many2one("sale.order", ondelete="restrict", tracking=True)
    project_id = fields.Many2one("project.project", ondelete="restrict", tracking=True)
    programme_run_id = fields.Many2one("hjig.programme.run", ondelete="restrict", readonly=True)
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, default=lambda self: self.env.company
    )
    superseded_case_id = fields.Many2one(
        "hjig.sseries.case", readonly=True, copy=False, ondelete="restrict", index=True,
        string="Supersedes Case",
    )
    superseded_by_case_ids = fields.One2many(
        "hjig.sseries.case", "superseded_case_id", readonly=True, string="Superseding Cases",
    )
    supersession_reason = fields.Selection(
        [
            ("legal_entity", "Legal entity change"),
            ("programme_scope", "Programme scope change"),
            ("commercial_identity", "Commercial identity change"),
        ],
        readonly=True,
        copy=False,
    )
    reopen_count = fields.Integer(default=0, readonly=True, copy=False)
    active_intake_project_key = fields.Char(readonly=True, copy=False, index=True)

    _active_intake_project_case_unique = models.Constraint(
        "UNIQUE(active_intake_project_key) DEFERRABLE INITIALLY DEFERRED",
        "An intake project can have only one active S-Series case.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.context.get("hjig_sseries_ingest") or self.env.context.get("hjig_sseries_supersede")):
            raise UserError(_("S-Series cases must originate from governed intake or promotion actions."))
        for vals in vals_list:
            if not vals.get("active_intake_project_key"):
                intake_project_id = vals.get("intake_project_id")
                if not intake_project_id:
                    raise ValidationError(_("An intake project is required for an S-Series case."))
                vals["active_intake_project_key"] = "intake-project-%s" % intake_project_id
        return super().create(vals_list)

    def write(self, vals):
        frozen = {
            "name", "submission_id", "intake_project_id", "customer_name", "project_name", "company_id",
        }
        if frozen.intersection(vals):
            raise ValidationError(_("S-Series intake provenance cannot be changed."))
        supersession_fields = {
            "superseded_case_id", "supersession_reason", "active_intake_project_key",
        }
        if supersession_fields.intersection(vals) and not self.env.context.get("hjig_sseries_supersede"):
            raise ValidationError(_("Use the governed S-Series supersession action."))
        if "stage" in vals and not self.env.context.get("hjig_sseries_workflow"):
            raise ValidationError(_("Use governed S-Series actions to change stage."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("An S-Series case cannot be deleted; use a governed cancellation action."))

    def action_assign_to_me(self):
        self.write({"owner_id": self.env.user.id})
        return True

    def action_start_internal_review(self):
        for case in self:
            if case.stage != "s0_received":
                raise UserError(_("Only an S0 received case can start internal review."))
            case.with_context(hjig_sseries_workflow=True).write({
                "stage": "s1_review",
                "owner_id": case.owner_id.id or self.env.user.id,
                "reviewer_id": self.env.user.id,
                "next_action": _("Confirm customer identity, scope facts and programme route"),
            })
        return True
