"""Read-only audit of active staging internal users and S-Series group membership."""

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
        cursor.execute(
            """
            SELECT u.id, p.name, u.login,
                   bool_or(imd.name = 'group_hjig_sseries_user') AS is_sseries_user,
                   bool_or(imd.name = 'group_hjig_sseries_manager') AS is_sseries_manager
              FROM res_users u
              JOIN res_partner p ON p.id = u.partner_id
         LEFT JOIN res_groups_users_rel rel ON rel.uid = u.id
         LEFT JOIN ir_model_data imd
                ON imd.model = 'res.groups'
               AND imd.res_id = rel.gid
               AND imd.module = 'new_hongyijig_custom'
             WHERE u.active = TRUE
               AND u.share = FALSE
          GROUP BY u.id, p.name, u.login
          ORDER BY u.id
            """
        )
        rows = cursor.fetchall()
finally:
    connection.close()

for user_id, name, login, is_user, is_manager in rows:
    print(
        "STAGING_USER id=%s name=%r login=%r sseries_user=%s sseries_manager=%s"
        % (user_id, name, login, bool(is_user), bool(is_manager))
    )
print("SSERIES_STAGING_USER_AUDIT_COMPLETE users=%s production=untouched" % len(rows))
