"""Odoo shell payload: give the Intake owner read/work access to the unified CRM S-Series panel."""

if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("Refusing non-staging database")

user = env["res.users"].search([("login", "=", "soniakhattar")], limit=1)
if not user:
    raise RuntimeError("Staging Intake user not found")

user_group = env.ref("new_hongyijig_custom.group_hjig_sseries_user")
user.write({"group_ids": [(4, user_group.id)]})
env.cr.commit()

if not user.has_group("new_hongyijig_custom.group_hjig_sseries_user"):
    raise RuntimeError("S-Series user-role verification failed")
if user.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
    raise RuntimeError("Intake user must not receive S-Series manager authority")

print(
    "SSERIES_STAGING_INTAKE_USER_GRANTED "
    "user=%s user_role=true manager_role=false production=untouched" % user.login
)
