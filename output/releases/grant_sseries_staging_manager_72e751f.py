"""Odoo shell payload: grant staging Intake user the S-Series manager role."""

user = env["res.users"].search([("login", "=", "soniakhattar")], limit=1)
if not user:
    raise RuntimeError("Staging Intake user not found")
manager_group = env.ref("new_hongyijig_custom.group_hjig_sseries_manager")
user.write({"group_ids": [(4, manager_group.id)]})
env.cr.commit()
if not user.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
    raise RuntimeError("S-Series manager role verification failed")
print(
    "SSERIES_STAGING_MANAGER_GRANTED "
    "user=%s manager=true production=untouched" % user.login
)
