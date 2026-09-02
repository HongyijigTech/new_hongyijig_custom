import base64
import uuid

from odoo.exceptions import ValidationError


Gateway = env["hjig.sseries.intake.attachment.gateway"].sudo()
suffix = uuid.uuid4().hex[:10].upper()
clean_submission = f"PB-SMOKE-{suffix}"
clean_payload = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"HJIG clean staging scanner smoke payload"
).decode("ascii")

before = Gateway.search_count([])
clean = Gateway.create({
    "client_submission_id": clean_submission,
    "client_project_id": "",
    "component_index": 1,
    "attachment_type": "REFERENCE_IMAGE",
    "file_name": "hjig-clean-smoke.png",
    "mime_type": "image/png",
    "file_base64": clean_payload,
})
if clean.upload_status != "scanned_clean_private":
    raise RuntimeError(f"Unexpected clean status: {clean.upload_status}")
if clean.scan_result != "clean" or clean.scan_engine != "clamdscan":
    raise RuntimeError(
        f"Unexpected clean scan evidence: {clean.scan_engine}/{clean.scan_result}"
    )
if not clean.attachment_id or clean.attachment_id.access_token:
    raise RuntimeError("Clean upload is missing private tokenless attachment evidence")

eicar = base64.b64encode(
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
).decode("ascii")
eicar_rejected = False
try:
    with env.cr.savepoint():
        Gateway.create({
            "client_submission_id": f"PB-EICAR-{suffix}",
            "client_project_id": "",
            "component_index": 1,
            "attachment_type": "TECHNICAL_FILE",
            "file_name": "hjig-eicar-smoke.txt",
            "mime_type": "text/plain",
            "file_base64": eicar,
        })
except ValidationError as error:
    eicar_rejected = "rejected by malware scanning" in str(error)
if not eicar_rejected:
    raise RuntimeError("EICAR smoke payload was not rejected by the Odoo gateway")
if Gateway.search_count([]) != before + 1:
    raise RuntimeError("Rejected malware payload created persistent gateway state")

print(
    "HJIG_STAGING_ATTACHMENT_GATEWAY_PASS "
    f"clean_status={clean.upload_status} engine={clean.scan_engine} "
    "eicar=rejected rejected_state_persisted=false production_untouched=true"
)
env.cr.rollback()
