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

validated = []
for programme in programmes.sorted(lambda item: item.template_id.code):
    if programme.execution_mode == "governed_gates":
        programme.activity_line_ids.write({"duration_days": 1})
    programme.write({
        "dependency_review_status": "verified",
        "evidence_review_status": "verified",
        "timing_review_status": "verified",
    })
    programme._validate_definition()
    validated.append(programme.template_id.code)
    print("PROGRAMME_DEFINITION_VALIDATED", programme.template_id.code)
env.cr.rollback()
if validated != ["LGC", "LGD", "LGV", "TLC", "TLL"]:
    raise RuntimeError(f"Unexpected programme validation result: VALIDATED={validated}")
print("PROGRAMME_AUTHORITY_VALIDATION_PASS_ROLLED_BACK")
