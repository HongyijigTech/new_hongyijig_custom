"""Read-only post-deployment check for the B-Series staging implementation."""

if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("This staging check is restricted to HongyijigTech_10Feb")

expected_activity_counts = {
    "LGC": 141,
    "LGD": 22,
    "LGV": 127,
    "TLC": 106,
    "TLL": 12,
}
expected_routes = {
    "LGC": ["PA-00", "TG-01", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09", "TG-10"],
    "LGD": ["PA-00", "LGD-SIGNOFF"],
    "LGV": ["PA-00", "PRE-B2", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09", "TG-10"],
    "TLC": ["PA-00", "PRE-B2", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-10-LITE"],
    "TLL": ["TLL-S01", "TLL-S02", "TLL-S03", "TLL-S04", "TLL-S05", "TLL-S06"],
}
expected_checklist_counts = {"LGC": 17, "LGD": 17, "LGV": 16, "TLC": 16, "TLL": 0}

Version = env["hjig.programme.template.version"]
Run = env["hjig.programme.run"]
programmes = Version.search([("template_id.code", "in", list(expected_activity_counts))])

if len(programmes) != 5:
    raise RuntimeError(f"Expected exactly five staging programme versions; found {len(programmes)}")

for programme in programmes.sorted(lambda item: item.template_id.code):
    code = programme.template_id.code
    actual = (len(programme.activity_line_ids), len(programme.dependency_rule_ids), len(programme.artifact_rule_ids))
    if actual[0] != expected_activity_counts[code]:
        raise RuntimeError(f"{code} activity count mismatch: expected {expected_activity_counts[code]}, found {actual[0]}")
    route = programme.gate_line_ids.sorted("sequence").mapped("stage_id.code")
    if route != expected_routes[code]:
        raise RuntimeError(f"{code} route mismatch: expected {expected_routes[code]}, found {route}")
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
    if not programme.activity_line_ids.filtered("required_artifact_ids"):
        raise RuntimeError(f"{code} has no activity-to-evidence mapping")
    if len(programme.checklist_item_ids) != expected_checklist_counts[code]:
        raise RuntimeError(
            f"{code} authoritative checklist count mismatch: "
            f"expected {expected_checklist_counts[code]}, found {len(programme.checklist_item_ids)}"
        )
    mould_stages = programme.gate_line_ids.filtered(
        lambda gate: gate.stage_id.code in {"TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09"}
    )
    if mould_stages.filtered(lambda gate: gate.execution_basis != "mould"):
        raise RuntimeError(f"{code} has a post-design technical gate that is not mould-basis")
    print(
        "STAGING_PROGRAMME_PASS", code, *actual,
        "CHECKLIST_ITEMS", len(programme.checklist_item_ids),
        "DRAFT_UNREVIEWED", "ROUTE", ",".join(route)
    )

print("STAGING_PROGRAMME_RUN_COUNT", Run.search_count([]))
print("STAGING_BSERIES_READ_ONLY_REGRESSION_PASS")
env.cr.rollback()
