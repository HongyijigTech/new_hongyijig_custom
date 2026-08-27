"""Read-only post-deployment check for the B-Series staging implementation."""

if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("This staging check is restricted to HongyijigTech_10Feb")

expected = {
    "LGC": (141, 1723, 94),
    "LGD": (22, 123, 18),
    "LGV": (127, 1377, 85),
    "TLC": (106, 1133, 70),
    "TLL": (12, 20, 12),
}

Version = env["hjig.programme.template.version"]
Run = env["hjig.programme.run"]
programmes = Version.search([("template_id.code", "in", list(expected))])

if len(programmes) != 5:
    raise RuntimeError(f"Expected exactly five staging programme versions; found {len(programmes)}")

for programme in programmes.sorted(lambda item: item.template_id.code):
    code = programme.template_id.code
    actual = (
        len(programme.activity_line_ids),
        len(programme.dependency_rule_ids),
        len(programme.artifact_rule_ids),
    )
    if actual != expected[code]:
        raise RuntimeError(f"{code} reconciliation mismatch: expected {expected[code]}, found {actual}")
    if programme.state != "draft" or programme.is_current:
        raise RuntimeError(f"{code} must remain a non-current draft pending governed review")
    if programme.dependency_review_status != "unreviewed" or programme.evidence_review_status != "unreviewed":
        raise RuntimeError(f"{code} review status changed without business approval")
    required_gates = programme.gate_line_ids.filtered("required")
    missing = required_gates.filtered(
        lambda gate: not programme.artifact_rule_ids.filtered(
            lambda rule: rule.stage_id == gate.stage_id and rule.mandatory
        )
    )
    if missing:
        raise RuntimeError(f"{code} has required gates without mandatory artifacts")
    print("STAGING_PROGRAMME_PASS", code, *actual, "DRAFT_UNREVIEWED")

print("STAGING_PROGRAMME_RUN_COUNT", Run.search_count([]))
print("STAGING_BSERIES_READ_ONLY_REGRESSION_PASS")
env.cr.rollback()
