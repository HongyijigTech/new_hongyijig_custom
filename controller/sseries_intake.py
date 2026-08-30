import hashlib
import hmac
import json
import logging
import time

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)
MAX_PAYLOAD_BYTES = 1_000_000
MAX_CLOCK_SKEW_SECONDS = 300


class SSeriesIntakeController(http.Controller):
    @http.route(
        "/api/v1/hjig/sseries/intake",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def receive_sseries_intake(self, **kwargs):
        if request.httprequest.mimetype != "application/json":
            return request.make_json_response(
                {"ok": False, "error": "content_type_must_be_json"}, status=415
            )
        raw_body = request.httprequest.get_data(cache=False, as_text=False)
        if not raw_body or len(raw_body) > MAX_PAYLOAD_BYTES:
            return request.make_json_response(
                {"ok": False, "error": "invalid_payload_size"}, status=413
            )

        timestamp = request.httprequest.headers.get("X-Hongyi-Timestamp", "").strip()
        signature = request.httprequest.headers.get("X-Hongyi-Signature", "").strip().lower()
        secret = request.env["ir.config_parameter"].sudo().get_param(
            "hjig.sseries.intake_hmac_secret"
        )
        if not secret:
            _logger.error("S-Series intake refused because HMAC secret is not configured")
            return request.make_json_response(
                {"ok": False, "error": "service_not_configured"}, status=503
            )
        try:
            request_time = int(timestamp)
        except (TypeError, ValueError):
            return request.make_json_response(
                {"ok": False, "error": "invalid_signature"}, status=401
            )
        if abs(int(time.time()) - request_time) > MAX_CLOCK_SKEW_SECONDS:
            return request.make_json_response(
                {"ok": False, "error": "expired_signature"}, status=401
            )
        signed_message = timestamp.encode("utf-8") + b"." + raw_body
        expected = hmac.new(secret.encode("utf-8"), signed_message, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            return request.make_json_response(
                {"ok": False, "error": "invalid_signature"}, status=401
            )

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return request.make_json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )

        try:
            result = request.env["hjig.sseries.intake.submission"].sudo().ingest_payload(
                payload, signature_timestamp=timestamp
            )
        except ValidationError as error:
            request.env.cr.rollback()
            return request.make_json_response(
                {"ok": False, "error": "validation_failed", "message": str(error)}, status=422
            )
        except Exception:
            request.env.cr.rollback()
            _logger.exception("Unexpected S-Series intake failure")
            return request.make_json_response(
                {"ok": False, "error": "intake_failed"}, status=500
            )

        submission = result["submission"]
        return request.make_json_response({
            "ok": True,
            "submission_reference": submission.client_submission_id,
            "status": "received",
            "project_count": submission.project_count,
            "idempotent": result["idempotent"],
        })
