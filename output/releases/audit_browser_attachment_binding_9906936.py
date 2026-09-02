"""Read-only audit for the real Programme Builder browser attachment regression."""

import configparser

import psycopg2


SUBMISSION_REFERENCE = "PB-MTG61N4X-H2MFV"
PORTFOLIO_REFERENCE = "PG-MTG29OF2-EKGU7"

config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
connection = psycopg2.connect(
    host=options.get("db_host", "localhost"),
    port=options.get("db_port", "5432"),
    user=options.get("db_user", "hongyijig"),
    password=options.get("db_password", ""),
    dbname="HongyijigTech_10Feb",
)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT g.name,
                   g.upload_status,
                   g.file_name,
                   g.file_size_bytes,
                   g.attachment_id,
                   a.public,
                   a.access_token,
                   s.client_submission_id,
                   p.client_project_id,
                   c.component_index,
                   c.reference_image_attachment_id,
                   a.res_model,
                   a.res_id,
                   COUNT(sc.id),
                   COUNT(sc.lead_id)
              FROM hjig_sseries_intake_submission s
              JOIN hjig_sseries_intake_project p ON p.submission_id = s.id
              JOIN hjig_sseries_intake_component c ON c.project_id = p.id
              JOIN hjig_sseries_intake_attachment_gateway g
                ON g.submission_id = s.id
               AND g.project_id = p.id
               AND g.component_id = c.id
              JOIN ir_attachment a ON a.id = g.attachment_id
              LEFT JOIN hjig_sseries_case sc ON sc.submission_id = s.id
             WHERE s.client_submission_id = %s
             GROUP BY g.name, g.upload_status, g.file_name, g.file_size_bytes,
                      g.attachment_id, a.public, a.access_token,
                      s.client_submission_id, p.client_project_id,
                      c.component_index, c.reference_image_attachment_id,
                      a.res_model, a.res_id
            """,
            (SUBMISSION_REFERENCE,),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected exactly one bound browser attachment, found {len(rows)}"
            )
        (
            attachment_reference,
            upload_status,
            file_name,
            file_size_bytes,
            gateway_attachment_id,
            is_public,
            access_token,
            submission_reference,
            project_reference,
            component_index,
            component_attachment_id,
            attachment_res_model,
            attachment_res_id,
            case_count,
            lead_count,
        ) = rows[0]
        if upload_status != "stored_private_uat":
            raise RuntimeError(f"Unexpected upload status: {upload_status}")
        if file_name != "meta_valid.png" or not file_size_bytes:
            raise RuntimeError("Browser file metadata was not preserved")
        if is_public or access_token:
            raise RuntimeError("Browser attachment must be private without a public token")
        if submission_reference != SUBMISSION_REFERENCE:
            raise RuntimeError("Attachment was bound to the wrong submission")
        if project_reference != SUBMISSION_REFERENCE or component_index != 1:
            raise RuntimeError("Attachment was bound to the wrong project/component")
        if component_attachment_id != gateway_attachment_id:
            raise RuntimeError("Component attachment pointer does not match the gateway")
        if attachment_res_model != "hjig.sseries.intake.component" or not attachment_res_id:
            raise RuntimeError("File was not rebound to the immutable component snapshot")
        if case_count != 1 or lead_count != 1:
            raise RuntimeError("Website submission did not create exactly one CRM opportunity")
        cursor.execute(
            """
            SELECT s.form_type,
                   COUNT(DISTINCT p.id),
                   COUNT(DISTINCT sc.id),
                   COUNT(DISTINCT sc.lead_id)
              FROM hjig_sseries_intake_submission s
              JOIN hjig_sseries_intake_project p ON p.submission_id = s.id
              LEFT JOIN hjig_sseries_case sc ON sc.submission_id = s.id
             WHERE s.client_submission_id = %s
             GROUP BY s.form_type
            """,
            (PORTFOLIO_REFERENCE,),
        )
        portfolio_row = cursor.fetchone()
        if portfolio_row != ("portfolio_guard", 1, 1, 1):
            raise RuntimeError(
                f"PortfolioGuard browser regression mismatch: {portfolio_row!r}"
            )
finally:
    connection.rollback()
    connection.close()

print(
    "SSERIES_BROWSER_ATTACHMENT_BINDING_PASS "
    f"submission={SUBMISSION_REFERENCE} reference={attachment_reference} "
    f"file={file_name} bytes={file_size_bytes} private=yes public_token=no "
    f"component=1 crm_opportunities=1 portfolio={PORTFOLIO_REFERENCE} "
    "portfolio_projects=1 portfolio_cases=1 portfolio_crm_opportunities=1 "
    "production=untouched"
)
