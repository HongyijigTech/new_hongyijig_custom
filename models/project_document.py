# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PROJECT_CODE_PATTERN = re.compile(r"^HJ-[A-Z0-9]{2,6}-\d{4}-\d{4}$")


class ProjectProject(models.Model):
    _inherit = "project.project"

    # This field already exists as a manual field in production. Defining it in the
    # governed module makes the rule portable to staging and future databases while
    # retaining the existing production column and technical name.
    x_project_code = fields.Char(
        string="Project Code",
        copy=False,
        index=True,
        tracking=True,
        help="Stable customer-project identifier. Format: HJ-PROGRAMME-YYYY-NNNN.",
    )
    hjig_project_record_type = fields.Selection(
        [
            ("unclassified", "Unclassified / Legacy"),
            ("programme_template", "Programme Template"),
            ("test", "Test / Validation"),
            ("customer", "Customer Project"),
        ],
        string="Project Record Type",
        default="unclassified",
        required=True,
        tracking=True,
        copy=False,
    )
    hjig_document_ids = fields.One2many(
        "hjig.project.document",
        "project_id",
        string="Controlled Documents",
    )
    hjig_document_count = fields.Integer(
        compute="_compute_hjig_document_count",
        string="Controlled Documents",
    )

    _x_project_code_unique = models.Constraint(
        "UNIQUE(x_project_code)",
        "Project Code must be unique.",
    )

    @api.depends("hjig_document_ids")
    def _compute_hjig_document_count(self):
        for project in self:
            project.hjig_document_count = self.env["hjig.project.document"].search_count([
                ("project_id", "=", project.id),
            ])

    @api.constrains("x_project_code", "hjig_project_record_type")
    def _check_project_code_governance(self):
        for project in self:
            code = (project.x_project_code or "").strip().upper()
            if project.hjig_project_record_type == "customer" and not code:
                raise ValidationError(_("A Customer Project must have a Project Code."))
            if code and not PROJECT_CODE_PATTERN.fullmatch(code):
                raise ValidationError(
                    _("Project Code must use the format HJ-PROGRAMME-YYYY-NNNN, for example HJ-LGC-2026-0001.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("x_project_code"):
                vals["x_project_code"] = vals["x_project_code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("x_project_code"):
            vals["x_project_code"] = vals["x_project_code"].strip().upper()
        if "x_project_code" in vals:
            new_code = vals.get("x_project_code") or False
            for project in self:
                if project.x_project_code != new_code and project.hjig_document_ids:
                    raise ValidationError(
                        _("Project Code cannot be changed after controlled documents exist. Create an approved correction instead.")
                    )
        return super().write(vals)

    def action_open_customer_documents(self):
        self.ensure_one()
        return self._hjig_document_action("customer")

    def action_open_programme_documents(self):
        self.ensure_one()
        return self._hjig_document_action("programme_internal")

    def _hjig_document_action(self, register_type):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "new_hongyijig_custom.action_hjig_project_document_all"
        )
        action.update({
            "domain": [("project_id", "=", self.id), ("register_type", "=", register_type)],
            "context": {
                "default_project_id": self.id,
                "default_register_type": register_type,
            },
        })
        return action


class HjigProjectDocument(models.Model):
    _name = "hjig.project.document"
    _description = "Controlled Project Document Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, register_id desc"
    _rec_name = "register_id"

    register_id = fields.Char(
        string="Register ID",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        index=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    project_code = fields.Char(
        related="project_id.x_project_code",
        string="Project Code",
        store=True,
        readonly=True,
        index=True,
    )
    register_type = fields.Selection(
        [
            ("customer", "Customer Documents"),
            ("programme_internal", "Programme / Internal Documents"),
        ],
        required=True,
        index=True,
        tracking=True,
    )
    artifact_master_id = fields.Many2one(
        "hjig.governance.artifact.master",
        string="SOP / Form Master",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    stage_id = fields.Many2one(
        "hjig.launchguard.stage",
        string="LaunchGuard Stage",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    mould_id = fields.Many2one(
        "x_mould",
        string="Mould Scope",
        ondelete="restrict",
        index=True,
        tracking=True,
        help="Required for per-mould gate evidence; leave blank for project-basis evidence.",
    )
    document_class = fields.Selection(
        [
            ("master_reference", "Master / Reference"),
            ("customer_controlled", "Customer-Controlled"),
            ("project_working", "Project Working Document"),
            ("evidence", "Evidence"),
            ("approved_deliverable", "Approved Deliverable"),
        ],
        string="Document Classification",
        required=True,
        index=True,
        tracking=True,
    )
    title = fields.Char(required=True, tracking=True)
    document_type = fields.Char(required=True, tracking=True)
    external_document_number = fields.Char(string="Customer / External Document No.", tracking=True)
    revision = fields.Char(required=True, tracking=True)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
            ("superseded", "Superseded"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation",
        string="Owner Designation",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation",
        string="Approver Designation",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    owner_id = fields.Many2one(
        "res.users",
        string="Prepared / Submitted By",
        readonly=True,
        copy=False,
        tracking=True,
        help="Audit actor captured when the record is created or submitted. Governance ownership is controlled by designation.",
    )
    approver_id = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
        copy=False,
        tracking=True,
        help="Audit actor captured on approval. Approval authority is controlled by designation.",
    )
    effective_date = fields.Date(tracking=True)
    drive_url = fields.Char(string="Controlled Drive Link", required=True, tracking=True)
    sor_reference = fields.Char(string="SOR Reference", tracking=True)
    gate_reference = fields.Char(string="Gate Reference", tracking=True)
    ecn_reference = fields.Char(string="ECN / Change Reference", tracking=True)
    supersedes_id = fields.Many2one(
        "hjig.project.document",
        string="Supersedes",
        ondelete="restrict",
        tracking=True,
    )
    superseded_by_id = fields.Many2one(
        "hjig.project.document",
        string="Superseded By",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    notes = fields.Text()

    _register_id_unique = models.Constraint(
        "UNIQUE(register_id)",
        "Register ID must be unique.",
    )
    _project_revision_unique = models.Constraint(
        "UNIQUE(project_id, register_type, title, revision)",
        "The same document title and revision already exists in this project register.",
    )

    _CONTROLLED_FIELDS = {
        "register_id", "project_id", "artifact_master_id", "stage_id", "register_type",
        "document_class", "title", "document_type", "external_document_number", "revision",
        "owner_designation_id", "approver_designation_id", "owner_id", "approver_id",
        "effective_date", "drive_url", "sor_reference", "gate_reference", "mould_id",
        "ecn_reference", "supersedes_id", "superseded_by_id", "notes", "status",
    }

    @api.constrains("project_id", "mould_id")
    def _check_mould_scope(self):
        for document in self.filtered("mould_id"):
            if document.mould_id.x_project_id != document.project_id:
                raise ValidationError(_("The controlled-document mould must belong to the same project."))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            project = self.env["project.project"].browse(vals.get("project_id")).exists()
            if not project or not project.x_project_code:
                raise ValidationError(_("A controlled document requires a Project with a valid Project Code."))
            artifact = self.env["hjig.governance.artifact.master"].browse(
                vals.get("artifact_master_id")
            ).exists()
            if not artifact:
                raise ValidationError(_("A controlled document requires an SOP / Form Master."))
            vals.setdefault("register_type", artifact.default_register_type)
            vals.setdefault("document_class", artifact.default_document_class)
            vals.setdefault("title", artifact.name)
            artifact_labels = dict(
                artifact._fields["artifact_type"]._description_selection(self.env)
            )
            vals.setdefault("document_type", artifact_labels.get(artifact.artifact_type))
            vals.setdefault("owner_designation_id", artifact.owner_designation_id.id)
            vals.setdefault("approver_designation_id", artifact.approver_designation_id.id)
            vals.setdefault("owner_id", self.env.user.id)
            vals["status"] = "draft"
            if vals.get("register_id", _("New")) == _("New"):
                vals["register_id"] = sequence.next_by_code("hjig.project.document") or _("New")
        return super().create(vals_list)

    @api.constrains(
        "artifact_master_id",
        "stage_id",
        "register_type",
        "document_class",
        "owner_designation_id",
        "approver_designation_id",
    )
    def _check_master_and_designation_governance(self):
        for document in self:
            artifact = document.artifact_master_id
            if document.stage_id not in artifact.applicable_stage_ids:
                raise ValidationError(
                    _("The selected SOP/Form is not applicable to this LaunchGuard stage.")
                )
            if document.register_type != artifact.default_register_type:
                raise ValidationError(_("Register Type must follow the selected SOP/Form Master."))
            if document.document_class != artifact.default_document_class:
                raise ValidationError(_("Document Classification must follow the selected SOP/Form Master."))
            if document.owner_designation_id != artifact.owner_designation_id:
                raise ValidationError(_("Owner Designation must follow the selected SOP/Form Master."))
            if document.approver_designation_id != artifact.approver_designation_id:
                raise ValidationError(_("Approver Designation must follow the selected SOP/Form Master."))
            if document.owner_designation_id == document.approver_designation_id:
                raise ValidationError(_("Owner and approver designations must be different."))

    @api.constrains("register_type", "document_class")
    def _check_register_classification(self):
        for document in self:
            if document.register_type == "customer" and document.document_class in (
                "master_reference", "project_working"
            ):
                raise ValidationError(
                    _("Master/reference and project-working files cannot be placed in the Customer Document Register.")
                )
            if document.register_type == "programme_internal" and document.document_class == "customer_controlled":
                raise ValidationError(
                    _("Customer-controlled files must be placed in the Customer Document Register.")
                )

    @api.constrains("drive_url")
    def _check_drive_url(self):
        allowed_prefixes = (
            "https://drive.google.com/",
            "https://docs.google.com/",
        )
        for document in self:
            if not (document.drive_url or "").strip().startswith(allowed_prefixes):
                raise ValidationError(
                    _("Controlled Drive Link must be a secure Google Drive or Google Docs URL.")
                )

    @api.constrains("supersedes_id", "project_id")
    def _check_supersedes_same_project(self):
        for document in self:
            if document.supersedes_id and document.supersedes_id.project_id != document.project_id:
                raise ValidationError(_("A document can only supersede another document in the same project."))
            if document.supersedes_id == document:
                raise ValidationError(_("A document cannot supersede itself."))
            if document.supersedes_id and (
                document.supersedes_id.register_type != document.register_type
                or document.supersedes_id.title != document.title
                or document.supersedes_id.document_type != document.document_type
            ):
                raise ValidationError(
                    _("A new revision must keep the same register, title, and document type as the document it supersedes.")
                )

    def write(self, vals):
        if "status" in vals and not self.env.context.get("allow_document_workflow"):
            for document in self:
                if vals["status"] != document.status:
                    raise ValidationError(
                        _("Document status may only change through the controlled workflow actions.")
                    )
        if not self.env.context.get("allow_document_supersede"):
            changed = self._CONTROLLED_FIELDS.intersection(vals)
            locked = self.filtered(lambda document: document.status in ("approved", "superseded"))
            if changed and locked:
                raise ValidationError(
                    _("Approved or superseded documents are read-only. Create a new revision and use an ECN/change reference.")
                )
        return super().write(vals)

    def unlink(self):
        if any(document.status != "draft" for document in self):
            raise UserError(_("Only Draft document-register entries may be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for document in self:
            if document.status != "draft":
                raise UserError(_("Only Draft documents can be submitted for review."))
            if self.env.user not in document.owner_designation_id.holder_ids:
                raise UserError(
                    _("Only a current holder of the Owner Designation may submit this document.")
                )
            document.with_context(allow_document_workflow=True).write({
                "owner_id": self.env.user.id,
                "status": "review",
            })

    def action_approve(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_document_controller"):
            raise UserError(_("Only authorised Document Control users may approve controlled documents."))
        for document in self:
            if document.status != "review":
                raise UserError(_("Only documents Under Review can be approved."))
            if self.env.user not in document.approver_designation_id.holder_ids:
                raise ValidationError(
                    _("Only a current holder of the Approver Designation may approve this document.")
                )
            if document.owner_designation_id == document.approver_designation_id:
                raise ValidationError(_("Owner and approver designations must be different."))
            if document.owner_id == self.env.user:
                raise ValidationError(_("The same user cannot submit and approve a document."))
            if not document.effective_date:
                raise ValidationError(_("Effective Date is required before approval."))
            if document.supersedes_id:
                if document.supersedes_id.status != "approved":
                    raise ValidationError(_("The superseded document must currently be Approved."))
                if not document.ecn_reference:
                    raise ValidationError(_("An ECN / Change Reference is required when superseding an approved document."))
                document.supersedes_id.with_context(
                    allow_document_supersede=True,
                    allow_document_workflow=True,
                ).write({
                    "status": "superseded",
                    "superseded_by_id": document.id,
                })
            document.with_context(allow_document_workflow=True).write({
                "approver_id": self.env.user.id,
                "status": "approved",
            })
