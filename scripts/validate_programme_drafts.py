"""Validate imported programme DNA inside an isolated B-Series test database.

Run through ``odoo-bin shell``.  The transaction is always rolled back so the
review flags used for validation never become business data.
"""

database_name = env.cr.dbname
if "BSeries_Test" not in database_name:
    raise RuntimeError("Programme draft validation is permitted only in an isolated B-Series test database")

Version = env["hjig.programme.template.version"]
programmes = Version.search([("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC", "TLL"])])

if len(programmes) != 5:
    raise RuntimeError(f"Expected exactly five programme versions; found {len(programmes)}")

held = []
for programme in programmes.sorted(lambda item: item.template_id.code):
    programme.write({
        "dependency_review_status": "verified",
        "evidence_review_status": "verified",
    })
    try:
        programme._validate_definition()
    except Exception as exc:
        message = str(exc).lower()
        expected_hold = (
            "pending checklist content" in message
            if programme.template_id.code == "TLL"
            else "mandatory checklist item" in message
        )
        if not expected_hold:
            raise
        held.append(programme.template_id.code)
        print("PROGRAMME_DEFINITION_HOLD", programme.template_id.code, str(exc))
        continue
    raise RuntimeError(f"{programme.template_id.code} must remain blocked until every gate checklist is authoritative")
env.cr.rollback()
if held != ["LGC", "LGD", "LGV", "TLC", "TLL"]:
    raise RuntimeError(f"Unexpected checklist governance result: HOLD={held}")
print("CHECKLIST_ARCHITECTURE_PASS_ALL_PROGRAMMES_CONTENT_HOLD_ROLLED_BACK")
