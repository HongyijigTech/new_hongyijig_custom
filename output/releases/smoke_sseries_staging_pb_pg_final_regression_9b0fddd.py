"""Final non-emailing PB + PortfolioGuard regression through staging HTTP intake."""

import configparser
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

import psycopg2


DATABASE = "HongyijigTech_10Feb"
ENDPOINT = "http://127.0.0.1:8070/api/v1/hjig/sseries/intake?db=" + DATABASE
PB_SUBMISSION_ID = "PB-ODOO-FINAL-UAT-20260830-E354C17"
PG_SUBMISSION_ID = "PG-ODOO-FINAL-UAT-20260830-E354C17"


def load_database_options():
    config = configparser.ConfigParser()
    config.read("/etc/odoo.conf")
    return config["options"]


def open_database(options):
    return psycopg2.connect(
        host=options.get("db_host", "localhost"),
        port=options.get("db_port", "5432"),
        user=options.get("db_user", "hongyijig"),
        password=options.get("db_password", ""),
        dbname=DATABASE,
    )


def canonical_body(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def post_signed(payload, secret):
    body = canonical_body(payload)
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256
    ).hexdigest()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hongyi-Timestamp": timestamp,
            "X-Hongyi-Signature": signature,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Unexpected signed intake HTTP status: %s" % response.status)
        return json.loads(response.read().decode("utf-8"))


def assert_unsigned_rejected(payload):
    request = urllib.request.Request(
        ENDPOINT,
        data=canonical_body(payload),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
        if error.code != 401 or body.get("error") != "invalid_signature":
            raise RuntimeError("Unsigned request was not safely rejected: %s %r" % (error.code, body))
        return
    raise RuntimeError("Unsigned request was unexpectedly accepted")


def assert_result(result, submission_id, project_count, expected_idempotent):
    expected = {
        "ok": True,
        "submission_reference": submission_id,
        "status": "received",
        "project_count": project_count,
        "idempotent": expected_idempotent,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise RuntimeError("Unexpected %s result for %s: %r" % (key, submission_id, result))


pb_payload = {
    "form_type": "PROGRAMME_BUILDER",
    "client_submission_id": PB_SUBMISSION_ID,
    "frontend_spec_version": "ProgrammeBuilder-V2",
    "submitted_at": "2026-08-30T21:20:00+05:30",
    "company_name": "Hongyi PB Final Staging UAT",
    "customer_contact_name": "Internal PB UAT Contact",
    "customer_email": "pb-final-no-send@example.invalid",
    "customer_country": "India",
    "project_name": "Programme Builder Final Regression",
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

pg_project_one = {
    "client_project_id": "PG-FINAL-PROJECT-001",
    "project_name": "PortfolioGuard Final Project One",
    "current_project_stage": "Supplier Selection",
    "expected_start_window": "Within 30 Days",
    "product_category": "Consumer Product",
    "duration_months": 9,
    "mould_count": 1,
    "tooling_value_status": "Not Known Yet",
    "engagement_model": "SOURCEBRIDGE_ONLY",
    "services": {"overseas_sourcing_supplier_development": True},
    "sourcebridge_details": {
        "project_level": {
            "sourcing_objective": "Validate a governed supplier route for final staging UAT",
            "sourcing_package_count": 1,
        },
        "components": [
            {
                "component_name": "Final UAT Control Housing",
                "component_type": "Plastic Component",
                "component_function": "Protect the control assembly",
                "preferred_solution_route": "Supplier RFQ and validation",
                "expected_year_1_quantity": 1000,
            }
        ],
    },
}
pg_project_two = json.loads(json.dumps(pg_project_one))
pg_project_two.update(
    {
        "client_project_id": "PG-FINAL-PROJECT-002",
        "project_name": "PortfolioGuard Final Project Two",
    }
)
pg_payload = {
    "form_type": "PORTFOLIOGUARD",
    "client_submission_id": PG_SUBMISSION_ID,
    "frontend_spec_version": "PortfolioGuard-v1.7",
    "submitted_at": "2026-08-30T21:20:00+05:30",
    "customer": {
        "company_name": "Hongyi PG Final Staging UAT",
        "customer_contact_name": "Internal PG UAT Contact",
        "customer_email": "pg-final-no-send@example.invalid",
        "customer_country": "India",
    },
    "portfolio": {"projects_defined_count": 2},
    "projects": [pg_project_one, pg_project_two],
    "consent_given": True,
}


options = load_database_options()
connection = open_database(options)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key, value FROM ir_config_parameter WHERE key IN (%s, %s)",
            ("hjig.sseries.intake_hmac_secret", "hjig.sseries.acknowledgement_mode"),
        )
        parameters = dict(cursor.fetchall())
finally:
    connection.close()

secret = parameters.get("hjig.sseries.intake_hmac_secret")
if not secret:
    raise RuntimeError("Staging HMAC secret is not configured")
if parameters.get("hjig.sseries.acknowledgement_mode", "off") != "off":
    raise RuntimeError("Acknowledgement mode must be off during final staging regression")

assert_unsigned_rejected(pb_payload)
pb_first = post_signed(pb_payload, secret)
pb_second = post_signed(pb_payload, secret)
pg_first = post_signed(pg_payload, secret)
pg_second = post_signed(pg_payload, secret)

assert_result(pb_first, PB_SUBMISSION_ID, 1, False)
assert_result(pb_second, PB_SUBMISSION_ID, 1, True)
assert_result(pg_first, PG_SUBMISSION_ID, 2, False)
assert_result(pg_second, PG_SUBMISSION_ID, 2, True)

connection = open_database(options)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.client_submission_id,
                   COUNT(DISTINCT p.id) AS project_count,
                   COUNT(DISTINCT c.id) AS case_count,
                   COUNT(DISTINCT c.lead_id) AS lead_count,
                   MIN(c.stage) AS minimum_stage,
                   MAX(c.stage) AS maximum_stage,
                   MIN(s.acknowledgement_state) AS acknowledgement_state,
                   COUNT(DISTINCT s.acknowledgement_mail_id) AS acknowledgement_mail_count
              FROM hjig_sseries_intake_submission s
              LEFT JOIN hjig_sseries_intake_project p ON p.submission_id = s.id
              LEFT JOIN hjig_sseries_case c ON c.submission_id = s.id
             WHERE s.client_submission_id IN (%s, %s)
             GROUP BY s.client_submission_id
             ORDER BY s.client_submission_id
            """,
            (PB_SUBMISSION_ID, PG_SUBMISSION_ID),
        )
        rows = {row[0]: row[1:] for row in cursor.fetchall()}
finally:
    connection.close()

expected_rows = {
    PB_SUBMISSION_ID: (1, 1, 1, "s0_received", "s0_received", "pending", 0),
    PG_SUBMISSION_ID: (2, 2, 1, "s0_received", "s0_received", "pending", 0),
}
if rows != expected_rows:
    raise RuntimeError("Staging persistence verification failed: %r" % rows)

print(
    "SSERIES_FINAL_STAGING_REGRESSION_PASS "
    "pb_projects=1 pb_cases=1 pg_projects=2 pg_cases=2 "
    "crm_leads=2 duplicate_safe=yes unsigned_rejected=yes acknowledgement=off "
    "production=untouched"
)
