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
held = []
for programme in programmes.sorted(lambda item: item.template_id.code):
    programme.write({
        "dependency_review_status": "verified",
        "evidence_review_status": "verified",
    })
    if programme.template_id.code == "TLL":
        try:
            programme._validate_definition()
        except Exception as exc:
            if "pending checklist content" not in str(exc).lower():
                raise
            held.append(programme.template_id.code)
            print("PROGRAMME_DEFINITION_HOLD", programme.template_id.code, "PENDING_CHECKLIST_CONTENT")
            continue
        raise RuntimeError("TLL must remain blocked while its source checklist content is pending")
    programme._validate_definition()
    required_gates = programme.gate_line_ids.filtered("required")
    missing_artifact_gates = required_gates.filtered(
        lambda gate: not programme.artifact_rule_ids.filtered(
            lambda rule: rule.stage_id == gate.stage_id and rule.mandatory
        )
    )
    if missing_artifact_gates:
        raise RuntimeError(
            f"{programme.template_id.code} has required gates without governed artifacts: "
            f"{', '.join(missing_artifact_gates.mapped('stage_id.code'))}"
        )
    print(
        "PROGRAMME_DEFINITION_PASS",
        programme.template_id.code,
        len(programme.activity_line_ids),
        len(programme.dependency_rule_ids),
        len(programme.artifact_rule_ids),
    )
    validated.append(programme.template_id.code)

env.cr.rollback()
if validated != ["LGC", "LGD", "LGV", "TLC"] or held != ["TLL"]:
    raise RuntimeError(f"Unexpected validation result: PASS={validated}, HOLD={held}")
print("FOUR_BSERIES_PROGRAMMES_PASS_TLL_GOVERNANCE_HOLD_ROLLED_BACK")
