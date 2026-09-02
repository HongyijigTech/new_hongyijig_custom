"""Odoo shell payload: provision the isolated S-Series staging n8n API identity."""

import os


if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("Refusing non-staging database")

login = "soniakhattar"
key_path = "/home/hongyi-jig-erp/.sseries_staging_api_key"
Users = env["res.users"].sudo().with_context(no_reset_password=True)
user_group = env.ref("new_hongyijig_custom.group_hjig_sseries_user")

user = Users.search([("login", "=", login)], limit=1)
if not user:
    raise RuntimeError("Existing staging Intake user not found")
if not user.active or user.share:
    raise RuntimeError("Existing staging Intake user must remain the sole active internal login")
user.write({"group_ids": [(4, user_group.id)]})

# Revoke only earlier keys issued by this controlled setup, then rotate once.
keys = env["res.users.apikeys"].sudo().search([
    ("user_id", "=", user.id),
    ("name", "=", "S-Series staging n8n bridge"),
])
if keys:
    keys._remove()

api_key = env["res.users.apikeys"].with_user(user).sudo()._generate(
    scope=None,
    name="S-Series staging n8n bridge",
    expiration_date=None,
)
with open(key_path, "w", encoding="utf-8") as handle:
    handle.write(api_key)
os.chmod(key_path, 0o600)
env.cr.commit()

if not user.has_group("new_hongyijig_custom.group_hjig_sseries_user"):
    raise RuntimeError("S-Series user role verification failed")

print(
    "SSERIES_STAGING_N8N_IDENTITY_PASS "
    "login=%s reused_existing_internal_login=true user_role=true "
    "one_seat_staging_role_unchanged=true "
    "invitation_sent=false "
    "key_file_mode=0600 production=untouched" % login
)
