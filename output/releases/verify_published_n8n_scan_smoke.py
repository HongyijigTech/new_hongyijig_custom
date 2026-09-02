Gateway = env["hjig.sseries.intake.attachment.gateway"].sudo()
clean = Gateway.search([
    ("client_submission_id", "=", "PB-N8NSMOKE-20260831A"),
], limit=1)
if not clean:
    raise RuntimeError("Published n8n clean smoke did not reach Odoo staging")
if clean.upload_status != "scanned_clean_private" or clean.scan_result != "clean":
    raise RuntimeError(
        f"Unexpected published n8n clean evidence: {clean.upload_status}/{clean.scan_result}"
    )
if clean.scan_engine != "clamdscan" or not clean.scan_completed_at:
    raise RuntimeError("Published n8n clean smoke lacks scanner evidence")
if not clean.attachment_id or clean.attachment_id.access_token:
    raise RuntimeError("Published n8n clean smoke is not private/tokenless")

eicar_count = Gateway.search_count([
    ("client_submission_id", "=", "PB-N8NEICAR-20260831A"),
])
if eicar_count:
    raise RuntimeError("Published n8n malware smoke created gateway state")

print(
    "HJIG_PUBLISHED_N8N_SCAN_GATE_PASS "
    f"clean_reference={clean.name} clean_status={clean.upload_status} "
    f"engine={clean.scan_engine} eicar_state_count={eicar_count} "
    "private=true tokenless=true production_untouched=true"
)
env.cr.rollback()
