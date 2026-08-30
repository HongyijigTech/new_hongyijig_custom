import base64
import binascii
import hashlib
import os
import re
import subprocess
import tempfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
DEFAULT_SCANNER_COMMAND = "/usr/bin/clamdscan"
DEFAULT_SCANNER_TIMEOUT_SECONDS = 30
MAX_SCANNER_TIMEOUT_SECONDS = 120
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
        [
            ("stored_private_uat", "Legacy Private — Unscanned / Blocked"),
            ("scanned_clean_private", "Malware Scan Clean — Private"),
        ],
        required=True,
        default="scanned_clean_private",
        readonly=True,
        copy=False,
    )
    scan_engine = fields.Char(readonly=True, copy=False)
    scan_result = fields.Selection(
        [("clean", "Clean")],
        readonly=True,
        copy=False,
    )
    scan_completed_at = fields.Datetime(readonly=True, copy=False)
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

    @api.model
    def _scanner_settings(self):
        parameters = self.env["ir.config_parameter"].sudo()
        command = str(
            parameters.get_param(
                "hjig.sseries.attachment_scanner_command", DEFAULT_SCANNER_COMMAND
            )
            or ""
        ).strip()
        if not command or not os.path.isabs(command):
            raise ValidationError(_("Attachment malware scanner is not configured safely."))
        raw_timeout = parameters.get_param(
            "hjig.sseries.attachment_scanner_timeout_seconds",
            str(DEFAULT_SCANNER_TIMEOUT_SECONDS),
        )
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Attachment malware scanner timeout is invalid.")) from error
        if not 1 <= timeout <= MAX_SCANNER_TIMEOUT_SECONDS:
            raise ValidationError(_("Attachment malware scanner timeout is outside the safe range."))
        return command, timeout

    @api.model
    def _scan_attachment_payload(self, raw_bytes, file_name):
        """Scan one file in a short-lived private quarantine before Odoo storage."""
        command, timeout = self._scanner_settings()
        if not os.path.isfile(command) or not os.access(command, os.X_OK):
            raise ValidationError(
                _("Attachment upload is unavailable because the malware scanner is not ready.")
            )
        suffix = "." + file_name.rsplit(".", 1)[1].lower()
        quarantine_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="hjig-sseries-quarantine-",
                suffix=suffix,
                delete=False,
            ) as quarantine:
                quarantine_path = quarantine.name
                os.chmod(quarantine_path, 0o600)
                quarantine.write(raw_bytes)
                quarantine.flush()
                os.fsync(quarantine.fileno())
            try:
                result = subprocess.run(
                    [command, "--fdpass", "--no-summary", quarantine_path],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ValidationError(
                    _("Attachment upload is unavailable because malware scanning did not complete.")
                ) from error
            if result.returncode == 1:
                raise ValidationError(_("Attachment was rejected by malware scanning."))
            if result.returncode != 0:
                raise ValidationError(
                    _("Attachment upload is unavailable because the malware scanner returned an error.")
                )
            return {
                "scan_engine": os.path.basename(command),
                "scan_result": "clean",
                "scan_completed_at": fields.Datetime.now(),
            }
        finally:
            if quarantine_path:
                try:
                    os.unlink(quarantine_path)
                except FileNotFoundError:
                    pass

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
        scan_values = self._scan_attachment_payload(raw_bytes, file_name)

        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        upload_key = hashlib.sha256(
            "|".join((submission_ref, project_ref, str(component_index), attachment_type, file_sha256)).encode()
        ).hexdigest()
        existing = self.search([("upload_key", "=", upload_key)], limit=1)
        if existing:
            if existing.upload_status != "scanned_clean_private" or existing.scan_result != "clean":
                existing.sudo().with_context(hjig_sseries_attachment_system_scan=True).write({
                    "upload_status": "scanned_clean_private",
                    **scan_values,
                })
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
            "upload_status": "scanned_clean_private",
            **scan_values,
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
            if gateway.upload_status != "scanned_clean_private" or gateway.scan_result != "clean":
                raise ValidationError(_("SourceBridge attachment has not passed malware scanning."))
            try:
                stored_bytes = base64.b64decode(gateway.attachment_id.sudo().datas or b"", validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValidationError(_("SourceBridge attachment storage integrity check failed.")) from error
            if hashlib.sha256(stored_bytes).hexdigest() != gateway.file_sha256:
                raise ValidationError(_("SourceBridge attachment changed after malware scanning."))
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
        if self.env.context.get("hjig_sseries_attachment_system_scan"):
            if set(vals) <= {"upload_status", "scan_engine", "scan_result", "scan_completed_at"}:
                return super().write(vals)
        if self.env.context.get("hjig_sseries_attachment_claim"):
            if set(vals) <= {"submission_id", "project_id", "component_id"}:
                return super().write(vals)
        raise UserError(_("S-Series attachment gateway records are immutable."))

    def unlink(self):
        raise UserError(_("S-Series attachment gateway records cannot be deleted."))
