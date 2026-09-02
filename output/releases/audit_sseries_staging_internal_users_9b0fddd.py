"""Odoo shell payload: read-only audit of active staging internal identities."""

if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("Refusing non-staging database")

manager_group = env.ref("new_hongyijig_custom.group_hjig_sseries_manager")
user_group = env.ref("new_hongyijig_custom.group_hjig_sseries_user")
users = env["res.users"].sudo().search([("active", "=", True), ("share", "=", False)])
for user in users.sorted("id"):
    print(
        "STAGING_INTERNAL_USER "
        "id=%s login=%s sseries_user=%s sseries_manager=%s"
        % (
            user.id,
            user.login,
            user_group in user.all_group_ids,
            manager_group in user.all_group_ids,
        )
    )
print("STAGING_INTERNAL_USER_COUNT count=%s production=untouched" % len(users))
env.cr.rollback()
