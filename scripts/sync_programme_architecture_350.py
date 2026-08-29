"""Apply Constitution v6.11 and Gate Forms v1.9 corrections to staging drafts."""

import os


isolated_db = os.environ.get("HJIG_ISOLATED_TEST_DB")
if env.cr.dbname != "HongyijigTech_10Feb" and not (
    isolated_db == env.cr.dbname
    and env.cr.dbname.startswith(("hongyijig_bseries_", "HongyijigTech_"))
    and "test" in env.cr.dbname.lower()
):
    raise RuntimeError("Programme architecture synchronisation is restricted to staging")

versions = env["hjig.programme.template.version"].search([
    ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC"]),
])
if len(versions) != 4 or versions.filtered(lambda version: version.state != "draft"):
    raise RuntimeError("Expected exactly four governed draft programme versions")

versions._sync_founder_approved_architecture()
versions._sync_founder_approved_activity_authority()
versions._sync_founder_approved_dependency_rules()
versions._sync_authoritative_gate_checklists()
env.cr.commit()

print("STAGING_PROGRAMME_ARCHITECTURE_350_SYNC=PASS")
for version in versions.sorted(lambda item: item.template_id.code):
    print(
        "PROGRAMME_350",
        version.template_id.code,
        len(version.activity_line_ids),
        len(version.dependency_rule_ids),
        len(version.artifact_rule_ids),
        len(version.checklist_item_ids),
    )
