import base64
import binascii
import hashlib
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE_EXTENSIONS = {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"}
TECHNICAL_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".csv", ".doc", ".docx", ".dwg", ".dxf", ".iges", ".igs", ".obj", ".pdf",
    ".ppt", ".pptx", ".step", ".stl", ".stp", ".txt", ".x_b", ".x_t", ".xls",
    ".xlsx", ".zip",
}
ALLOWED_TECHNICAL_MIME_TYPES = {
    "application/msword",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "text/csv",
    "text/plain",
}


class HjigSSeriesIntakeAttachmentGateway(models.Model):
    """Private, immutable pre-intake file transport for SourceBridge components."""

    _name = "hjig.sseries.intake.attachment.gateway"
    _description = "Governed S-Series SourceBridge Attachment Gateway"
    _order = "received_at desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    upload_key = fields.Char(required=True, readonly=True, copy=False, index=True)
    client_submission_id = fields.Char(required=True, readonly=True, copy=False, index=True)
    client_project_id = fields.Char(readonly=True, copy=False, index=True)
    component_index = fields.Integer(required=True, readonly=True, copy=False)
    attachment_type = fields.Selection(
        [("reference_image", "Reference Image"), ("technical_file", "Technical File")],
        required=True,
        readonly=True,
        copy=False,
    )
    file_name = fields.Char(required=True, readonly=True, copy=False)
    mime_type = fields.Char(required=True, readonly=True, copy=False)
    file_size_bytes = fields.Integer(required=True, readonly=True, copy=False)
    file_sha256 = fields.Char(required=True, readonly=True, copy=False, index=True)
    file_base64 = fields.Text(
        string="Inbound File Data",
        help="Write-only transport field. Base64 content is moved to a private ir.attachment.",
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        readonly=True,
        copy=False,
        ondelete="restrict",
        groups="new_hongyijig_custom.group_hjig_sseries_manager",
    )
    file_url = fields.Char(readonly=True, copy=False)
    upload_status = fields.Selection(
        [("stored_private_uat", "Stored Private — UAT Review")],
        required=True,
        default="stored_private_uat",
        readonly=True,
        copy=False,
    )
    submission_id = fields.Many2one(
        "hjig.sseries.intake.submission", readonly=True, copy=False, ondelete="restrict", index=True
    )
    project_id = fields.Many2one(
        "hjig.sseries.intake.project", readonly=True, copy=False, ondelete="restrict", index=True
    )
    component_id = fields.Many2one(
        "hjig.sseries.intake.component", readonly=True, copy=False, ondelete="restrict", index=True
    )
    received_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)

    _upload_key_unique = models.Constraint(
        "UNIQUE(upload_key)",
        "The same SourceBridge attachment upload may be stored only once.",
    )

    @api.model
    def _safe_identifier(self, value, label, allow_blank=False):
        text = str(value or "").strip()
        if not text and allow_blank:
            return ""
        if not (3 <= len(text) <= 120) or not SAFE_ID_RE.fullmatch(text):
            raise ValidationError(_("%s is invalid.") % label)
        return text

    @api.model
    def _safe_file_name(self, value):
        name = str(value or "").strip().replace("\\", "/").split("/")[-1]
        name = re.sub(r"[^A-Za-z0-9._() -]", "_", name).strip(" .")
        if not name or len(name) > 180 or "." not in name:
            raise ValidationError(_("Attachment filename is invalid."))
        return name

    @api.model
    def _validate_file_type(self, attachment_type, file_name, mime_type):
        extension = "." + file_name.rsplit(".", 1)[1].lower()
        if attachment_type == "reference_image":
            if extension not in IMAGE_EXTENSIONS or not mime_type.startswith("image/"):
                raise ValidationError(_("Reference image type is not allowed."))
            return
        if extension not in TECHNICAL_EXTENSIONS:
            raise ValidationError(_("Technical attachment extension is not allowed."))
        if not (mime_type.startswith("image/") or mime_type in ALLOWED_TECHNICAL_MIME_TYPES):
            raise ValidationError(_("Technical attachment MIME type is not allowed."))

    @api.model_create_multi
    def create(self, vals_list):
        if len(vals_list) != 1:
            raise ValidationError(_("Attachment gateway accepts one file per request."))
        vals = dict(vals_list[0])
        raw_base64 = vals.get("file_base64")
        if not isinstance(raw_base64, str) or not raw_base64.strip():
            raise ValidationError(_("Attachment file data is required."))
        if len(raw_base64) > ((MAX_ATTACHMENT_BYTES * 4 // 3) + 16):
            raise ValidationError(_("Attachment exceeds the 8 MB limit."))
        try:
            raw_bytes = base64.b64decode(raw_base64.strip(), validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationError(_("Attachment file data is not valid base64.")) from error
        if not raw_bytes or len(raw_bytes) > MAX_ATTACHMENT_BYTES:
            raise ValidationError(_("Attachment must contain between 1 byte and 8 MB."))

        submission_ref = self._safe_identifier(
            vals.get("client_submission_id"), _("Client submission ID")
        )
        if not submission_ref.startswith(("PB-", "PG-")):
            raise ValidationError(_("Client submission ID must start with PB- or PG-."))
        project_ref = self._safe_identifier(
            vals.get("client_project_id"), _("Client project ID"), allow_blank=True
        )
        if submission_ref.startswith("PB-") and project_ref:
            raise ValidationError(_("Programme Builder attachment must not supply a project ID."))
        if submission_ref.startswith("PG-") and not project_ref:
            raise ValidationError(_("PortfolioGuard attachment requires a project ID."))
        component_index = vals.get("component_index")
        if not isinstance(component_index, int) or isinstance(component_index, bool) or component_index < 1:
            raise ValidationError(_("Component index must be a positive whole number."))
        type_map = {"REFERENCE_IMAGE": "reference_image", "TECHNICAL_FILE": "technical_file"}
        attachment_type = type_map.get(str(vals.get("attachment_type") or "").upper())
        if not attachment_type:
            raise ValidationError(_("Attachment type is invalid."))
        file_name = self._safe_file_name(vals.get("file_name"))
        mime_type = str(vals.get("mime_type") or "application/octet-stream").lower().strip()
        self._validate_file_type(attachment_type, file_name, mime_type)

        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        upload_key = hashlib.sha256(
            "|".join((submission_ref, project_ref, str(component_index), attachment_type, file_sha256)).encode()
        ).hexdigest()
        existing = self.search([("upload_key", "=", upload_key)], limit=1)
        if existing:
            return existing
        public_reference = "ATT-" + upload_key[:24].upper()
        record = super().create({
            "name": public_reference,
            "upload_key": upload_key,
            "client_submission_id": submission_ref,
            "client_project_id": project_ref,
            "component_index": component_index,
            "attachment_type": attachment_type,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_size_bytes": len(raw_bytes),
            "file_sha256": file_sha256,
            "file_base64": False,
            "upload_status": "stored_private_uat",
        })
        attachment = self.env["ir.attachment"].sudo().create({
            "name": file_name,
            "datas": base64.b64encode(raw_bytes),
            "mimetype": mime_type,
            "res_model": record._name,
            "res_id": record.id,
            "description": "Private SourceBridge website intake attachment; no public token.",
        })
        record.sudo().with_context(hjig_sseries_attachment_system_write=True).write({
            "attachment_id": attachment.id,
            "file_url": "/web/content/%s?download=1" % attachment.id,
        })
        return record

    @api.model
    def claim_component_attachments(self, component, component_payload):
        binding_values = {}
        submission = component.project_id.submission_id
        expected_project_ref = "" if submission.form_type == "programme_builder" else component.project_id.client_project_id
        for prefix, attachment_type, field_name in (
            ("reference_image", "reference_image", "reference_image_attachment_id"),
            ("technical_file", "technical_file", "technical_file_attachment_id"),
        ):
            reference = str(component_payload.get(prefix + "_file_id") or "").strip()
            attached = bool(component_payload.get(prefix + "_attached") or reference)
            if not attached:
                continue
            if not reference:
                raise ValidationError(_("Attached SourceBridge file is missing its governed reference."))
            gateway = self.search([("name", "=", reference)], limit=1)
            if not gateway:
                raise ValidationError(_("SourceBridge attachment reference is not registered in Odoo."))
            expected = (
                gateway.client_submission_id == submission.client_submission_id
                and (gateway.client_project_id or "") == expected_project_ref
                and gateway.component_index == component.component_index
                and gateway.attachment_type == attachment_type
            )
            if not expected:
                raise ValidationError(_("SourceBridge attachment reference does not match this component."))
            if gateway.component_id and gateway.component_id != component:
                raise ValidationError(_("SourceBridge attachment is already bound to another component."))
            if not gateway.component_id:
                gateway.with_context(hjig_sseries_attachment_claim=True).write({
                    "submission_id": submission.id,
                    "project_id": component.project_id.id,
                    "component_id": component.id,
                })
                gateway.attachment_id.sudo().write({
                    "res_model": component._name,
                    "res_id": component.id,
                })
            binding_values[field_name] = gateway.attachment_id.id
        if binding_values:
            component.with_context(hjig_sseries_attachment_bind=True).write(binding_values)
        return True

    def write(self, vals):
        if self.env.context.get("hjig_sseries_attachment_system_write"):
            if set(vals) <= {"attachment_id", "file_url"}:
                return super().write(vals)
        if self.env.context.get("hjig_sseries_attachment_claim"):
            if set(vals) <= {"submission_id", "project_id", "component_id"}:
                return super().write(vals)
        raise UserError(_("S-Series attachment gateway records are immutable."))

    def unlink(self):
        raise UserError(_("S-Series attachment gateway records cannot be deleted."))
