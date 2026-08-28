# Native Forms deployment control

Version 1.27 replaces the superseded activity-dependency v1.2 enforcement in
draft B-Series programme DNA with Founder-approved v1.4 rules. It also migrates
B8 references to B8-01 through B8-09, preserves programme-specific routing, and
marks imported one-day activity durations as unbaselined rather than approved
delivery promises. Dependency, evidence and timing reviews remain unapproved
until their controlled business review is completed.

Version 1.7 promotes the existing `x_mould` and `x_mould_part` tables into
code-owned Odoo models. It retains the same tables, record IDs and existing SOR
relations.

Version 1.8.1 adds governed engineering reference databases and relational
dropdowns without deleting the legacy text snapshots:

- 26 plastic raw-material records and shrinkage guidance;
- 56 tool-steel records;
- 49 SPI, VDI and special-texture records;
- 18 cold/hot-runner gate records; and
- 15 inspection-method records.

Each imported master record carries workbook/tab/row lineage, revision,
designation authority and a controlled Draft/Approved/Superseded lifecycle.
Approved records cannot be rewritten. Mould-planning and dimensional forms copy
the selected reference values into the existing snapshot fields so historical
records remain readable even if a master is later superseded.

For a database where those models already exist as manual models:

1. Take and checksum a database backup and a deployed-module backup.
2. Record the existing mould and part IDs and business values.
3. Run `scripts/promote_legacy_mould_models.py` through `odoo-bin shell` before
   starting the 1.7 module-upgrade process.
Version 1.9 adds native Final Mould Plan, Risk Register, Issue Register and ECN
Register models. Their calculations and workflow controls replace workbook
formulas with traceable Odoo records while retaining source-tab lineage in the
SOP/Form Master.

Version 1.10 hardens these registers with Odoo-aligned project visibility,
API-safe workflow validation, record-bound attachments, validated evidence URLs,
immutable approved ECNs and source-exact Final Mould Plan snapshots.

4. Upgrade `new_hongyijig_custom` to 1.10. The pre-migration binds stable model
   XML IDs before access controls are loaded.
5. Verify legacy record IDs/values, the four native templates, the five
   engineering reference models, 164 imported baseline records, dropdown
   snapshots, project smart buttons and workflow tests.

On a database without the legacy manual models, skip step 3. Odoo creates the
code-owned models normally during module upgrade.
