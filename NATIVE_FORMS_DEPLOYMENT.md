# Native Forms 1.7 deployment control

Version 1.7 promotes the existing `x_mould` and `x_mould_part` tables into
code-owned Odoo models. It retains the same tables, record IDs and existing SOR
relations.

For a database where those models already exist as manual models:

1. Take and checksum a database backup and a deployed-module backup.
2. Record the existing mould and part IDs and business values.
3. Run `scripts/promote_legacy_mould_models.py` through `odoo-bin shell` before
   starting the 1.7 module-upgrade process.
4. Upgrade `new_hongyijig_custom` to 1.7. The pre-migration binds stable model
   XML IDs before access controls are loaded.
5. Verify legacy record IDs/values, the four native templates, new fields,
   project smart buttons and workflow tests.

On a database without the legacy manual models, skip step 3. Odoo creates the
code-owned models normally during module upgrade.
