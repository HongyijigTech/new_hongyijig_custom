"""Read-only audit of staging CRM stages, owner identities, and FD/P integrations."""

import configparser

import psycopg2


DATABASE = "HongyijigTech_10Feb"

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
        cursor.execute("SELECT id, name, sequence, fold FROM crm_stage ORDER BY sequence, id")
        for stage_id, name, sequence, fold in cursor.fetchall():
            print("CRM_STAGE id=%s name=%r sequence=%s fold=%s" % (stage_id, name, sequence, fold))
        cursor.execute(
            """
            SELECT u.id, p.name, u.login, p.email
              FROM res_users u
              JOIN res_partner p ON p.id = u.partner_id
             WHERE u.active = TRUE AND u.share = FALSE
          ORDER BY u.id
            """
        )
        for user_id, name, login, email in cursor.fetchall():
            print("CRM_OWNER id=%s name=%r login=%r email=%r" % (user_id, name, login, email))
        cursor.execute(
            """
            SELECT name, state
              FROM ir_module_module
             WHERE state = 'installed'
               AND (name ILIKE '%%fd%%' OR name ILIKE '%%p_series%%' OR name ILIKE '%%series%%')
          ORDER BY name
            """
        )
        for name, state in cursor.fetchall():
            print("CRM_MODULE name=%r state=%r" % (name, state))
        cursor.execute(
            """
            SELECT name, field_description, ttype, relation
              FROM ir_model_fields
             WHERE model = 'crm.lead'
               AND (name ILIKE '%%fd%%' OR name ILIKE '%%series%%' OR name ILIKE '%%programme%%')
          ORDER BY name
            """
        )
        for name, description, field_type, relation in cursor.fetchall():
            print(
                "CRM_FIELD name=%r description=%r type=%r relation=%r"
                % (name, description, field_type, relation)
            )
finally:
    connection.close()

print("STAGING_CRM_SPINE_AUDIT_COMPLETE production=untouched")
