import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


MAX_PAYLOAD_BYTES = 1_000_000


class HjigSSeriesIntakeGateway(models.Model):
    """Authenticated n8n bridge into the same immutable S-Series intake service."""

    _name = "hjig.sseries.intake.gateway"
    _description = "Governed S-Series n8n Intake Gateway Audit"
    _order = "received_at desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, index=True)
    client_submission_id = fields.Char(required=True, readonly=True, copy=False, index=True)
    form_type = fields.Selection(
        [("programme_builder", "Programme Builder"), ("portfolio_guard", "PortfolioGuard")],
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    payload_json = fields.Text(
        string="Inbound Payload",
        help="Write-only transport field. The gateway never persists raw payload text here.",
    )
    payload_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    submission_id = fields.Many2one(
        "hjig.sseries.intake.submission", required=True, readonly=True, copy=False, ondelete="restrict"
    )
    project_count = fields.Integer(required=True, readonly=True, copy=False)
    idempotent = fields.Boolean(required=True, readonly=True, copy=False)
    status = fields.Selection(
        [("received", "Received")], default="received", required=True, readonly=True, copy=False
    )
    received_at = fields.Datetime(required=True, readonly=True, copy=False, default=fields.Datetime.now)

    @api.model
    def _sanitize_public_payload(self, value, path="payload"):
        if isinstance(value, dict):
            clean = {}
            for key, child in value.items():
                key_text = str(key)
                if key_text.lower().startswith("odoo_"):
                    if child not in (None, "", False, 0, [], {}):
                        raise ValidationError(
                            _("Public website payload cannot supply an Odoo identifier (%s).")
                            % f"{path}.{key_text}"
                        )
                    continue
                clean[key] = self._sanitize_public_payload(child, f"{path}.{key_text}")
            return clean
        if isinstance(value, list):
            return [
                self._sanitize_public_payload(child, f"{path}[{index}]")
                for index, child in enumerate(value)
            ]
        return value

    @api.model_create_multi
    def create(self, vals_list):
        if len(vals_list) != 1:
            raise ValidationError(_("S-Series gateway accepts one submission per request."))
        raw = vals_list[0].get("payload_json")
        if not isinstance(raw, str) or not raw.strip():
            raise ValidationError(_("Inbound payload JSON is required."))
        if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValidationError(_("Inbound payload is too large."))
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValidationError(_("Inbound payload is not valid JSON.")) from error
        if not isinstance(decoded, dict):
            raise ValidationError(_("Inbound payload JSON must be an object."))
        payload = self._sanitize_public_payload(decoded)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result = self.env["hjig.sseries.intake.submission"].sudo().ingest_payload(
            payload, signature_timestamp="authenticated_n8n_gateway"
        )
        submission = result["submission"]
        return super().create({
            "name": "%s / n8n" % submission.client_submission_id,
            "client_submission_id": submission.client_submission_id,
            "form_type": submission.form_type,
            "payload_json": False,
            "payload_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "submission_id": submission.id,
            "project_count": submission.project_count,
            "idempotent": result["idempotent"],
            "status": "received",
        })

    def write(self, vals):
        raise UserError(_("S-Series gateway audit records are immutable."))

    def unlink(self):
        raise UserError(_("S-Series gateway audit records cannot be deleted."))
