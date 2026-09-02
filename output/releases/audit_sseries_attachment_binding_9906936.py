"""Read-only final audit of one synthetic SourceBridge attachment binding."""

import configparser

import psycopg2


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
                   g.file_size_bytes,
                   s.client_submission_id,
                   p.client_project_id,
                   c.component_index,
                   c.reference_image_attachment_id,
                   g.attachment_id,
                   a.res_model,
                   a.res_id,
                   a.access_token
              FROM hjig_sseries_intake_attachment_gateway g
              JOIN hjig_sseries_intake_submission s ON s.id = g.submission_id
              JOIN hjig_sseries_intake_project p ON p.id = g.project_id
              JOIN hjig_sseries_intake_component c ON c.id = g.component_id
              JOIN ir_attachment a ON a.id = g.attachment_id
             WHERE g.name = %s
            """,
            ("ATT-EF25475FC2AA85A8F3399995",),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Attachment gateway record was not bound to the final intake")
        (
            reference,
            status,
            size,
            submission_reference,
            project_reference,
            component_index,
            component_attachment_id,
            gateway_attachment_id,
            attachment_res_model,
            attachment_res_id,
            access_token,
        ) = row
        if status != "stored_private_uat" or size != 23:
            raise RuntimeError("Unexpected private attachment state")
        if submission_reference != "PB-ATTACHMENT-N8N-UAT-20260831-03":
            raise RuntimeError("Attachment was bound to the wrong submission")
        if project_reference != submission_reference or component_index != 1:
            raise RuntimeError("Attachment was bound to the wrong project/component")
        if component_attachment_id != gateway_attachment_id:
            raise RuntimeError("Component attachment pointer does not match the gateway")
        if attachment_res_model != "hjig.sseries.intake.component" or not attachment_res_id:
            raise RuntimeError("Private file was not rebound to the immutable component snapshot")
        if access_token:
            raise RuntimeError("Private intake attachment must not have a public access token")
finally:
    connection.rollback()
    connection.close()

print(
    "SSERIES_ATTACHMENT_BINDING_PASS "
    "reference=ATT-EF25475FC2AA85A8F3399995 private=yes public_token=no "
    "submission=PB-ATTACHMENT-N8N-UAT-20260831-03 component=1 production=untouched"
)
