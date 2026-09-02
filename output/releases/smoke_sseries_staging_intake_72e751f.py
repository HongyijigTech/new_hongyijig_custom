"""Create one non-emailing staging UAT intake through the real signed HTTP endpoint."""

import configparser
import hashlib
import hmac
import json
import time
import urllib.request

import psycopg2


DATABASE = "HongyijigTech_10Feb"
SUBMISSION_ID = "PB-ODOO-STAGING-UAT-20260830-01"


config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
connection = psycopg2.connect(
    host=options.get("db_host", "localhost"),
    port=options.get("db_port", "5432"),
    user=options.get("db_user", "hongyijig"),
    password=options.get("db_password", ""),
    dbname=DATABASE,
)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key, value FROM ir_config_parameter "
            "WHERE key IN (%s, %s)",
            ("hjig.sseries.intake_hmac_secret", "hjig.sseries.acknowledgement_mode"),
        )
        parameters = dict(cursor.fetchall())
finally:
    connection.close()

secret = parameters.get("hjig.sseries.intake_hmac_secret")
if not secret:
    raise RuntimeError("Staging HMAC secret is not configured")
if parameters.get("hjig.sseries.acknowledgement_mode", "off") != "off":
    raise RuntimeError("Staging acknowledgement mode must be off for this non-emailing smoke test")

payload = {
    "form_type": "PROGRAMME_BUILDER",
    "client_submission_id": SUBMISSION_ID,
    "frontend_spec_version": "ProgrammeBuilder-V2",
    "submitted_at": "2026-08-30T17:45:00+05:30",
    "company_name": "Hongyi S-Series Staging UAT",
    "customer_contact_name": "Internal UAT Contact",
    "customer_email": "uat-sseries-no-send@example.invalid",
    "customer_country": "India",
    "project_name": "Portfolio-to-B0 Employee Flow UAT",
    "current_project_stage": "Concept",
    "customer_stated_product_category": "Industrial",
    "customer_stated_mould_count": 1,
    "customer_expected_duration_months": 8,
    "tooling_value_status": "Not Known Yet",
    "engagement_model": "PROGRAMME_GOVERNANCE",
    "services": {"product_design": True},
    "existing_hongyi_commercial": {"already_contracted": False},
    "consent_given": True,
}
body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
timestamp = str(int(time.time()))
signature = hmac.new(
    secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256
).hexdigest()
request = urllib.request.Request(
    "http://127.0.0.1:8070/api/v1/hjig/sseries/intake?db=" + DATABASE,
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Hongyi-Timestamp": timestamp,
        "X-Hongyi-Signature": signature,
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=30) as response:
    result = json.loads(response.read().decode("utf-8"))
if not result.get("ok") or result.get("submission_reference") != SUBMISSION_ID:
    raise RuntimeError("Unexpected staging intake response: %r" % result)
print(
    "SSERIES_STAGING_SIGNED_INTAKE_PASS "
    "submission=%s projects=%s idempotent=%s acknowledgement=off production=untouched"
    % (SUBMISSION_ID, result.get("project_count"), result.get("idempotent"))
)
