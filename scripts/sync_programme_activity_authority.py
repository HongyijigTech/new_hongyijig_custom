"""Apply the locked v6.11 activity authority table to staging drafts."""

import os


isolated_db = os.environ.get("HJIG_ISOLATED_TEST_DB")
if env.cr.dbname != "HongyijigTech_10Feb" and not (
    isolated_db == env.cr.dbname
    and env.cr.dbname.startswith(("hongyijig_bseries_", "HongyijigTech_"))
    and "test" in env.cr.dbname.lower()
):
    raise RuntimeError("Activity authority synchronisation is restricted to staging")

versions = env["hjig.programme.template.version"].search([
    ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC"]),
])
if len(versions) != 4 or versions.filtered(lambda version: version.state != "draft"):
    raise RuntimeError("Expected exactly four governed draft programme versions")

versions._sync_founder_approved_activity_authority()
env.cr.commit()
print("STAGING_ACTIVITY_AUTHORITY_SYNC=PASS")
for version in versions.sorted(lambda item: item.template_id.code):
    print(
        "PROGRAMME_AUTHORITY",
        version.template_id.code,
        len(version.activity_line_ids),
        len(version.activity_line_ids.filtered("coordinator_designation_id")),
    )
