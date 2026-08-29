"""Read-only post-deployment check for the B-Series staging implementation."""

import os

from odoo.addons.new_hongyijig_custom.models.programme_activity_authority import (
    ACCOUNTING_SUPPORT_CODES,
    OWNER_BY_MASTER_CODE,
    SOURCE_REFERENCE,
    SOURCE_VERSION,
    _master_codes,
)

isolated_db = os.environ.get("HJIG_ISOLATED_TEST_DB")
if env.cr.dbname != "HongyijigTech_10Feb" and not (
    isolated_db == env.cr.dbname
    and env.cr.dbname.startswith(("hongyijig_bseries_", "HongyijigTech_"))
    and "test" in env.cr.dbname.lower()
):
    raise RuntimeError("This staging check is restricted to HongyijigTech_10Feb")

expected_activity_counts = {
    "LGC": 146,
    "LGD": 22,
    "LGV": 132,
    "TLC": 111,
    "TLL": 0,
}
expected_routes = {
    "LGC": ["PA-00", "TG-01", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09", "TG-10"],
    "LGD": ["PA-00", "LGD-SIGNOFF"],
    "LGV": ["PA-00", "PRE-B2", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09", "TG-10"],
    "TLC": ["PA-00", "PRE-B2", "TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-10-LITE"],
    "TLL": [],
}
expected_checklist_counts = {"LGC": 143, "LGD": 27, "LGV": 136, "TLC": 118, "TLL": 0}
expected_artifact_counts = {"LGC": 114, "LGD": 23, "LGV": 112, "TLC": 95, "TLL": 0}
expected_authority = {
    "A-017": "VENDOR-SOURCING",
    "A-024": "SR-TOOL-DESIGN",
    "A-026": "SR-DEVELOPMENT-CHINA",
    "A-042": "PROJECT-COORD",
    "A-043": "PROJECT-COORD",
    "B8-01": "SR-TOOL-DEVELOPMENT",
    "CM-05": "COMMERCIAL-LOGISTICS",
}

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
    if actual[2] != expected_artifact_counts[code]:
        raise RuntimeError(
            f"{code} artifact-rule count mismatch: "
            f"expected {expected_artifact_counts[code]}, found {actual[2]}"
        )
    route = programme.gate_line_ids.sorted("sequence").mapped("stage_id.code")
    if route != expected_routes[code]:
        raise RuntimeError(f"{code} route mismatch: expected {expected_routes[code]}, found {route}")
    if programme.state != "draft" or programme.is_current:
        raise RuntimeError(f"{code} must remain a non-current draft pending governed review")
    if (
        programme.dependency_review_status != "unreviewed"
        or programme.evidence_review_status != "unreviewed"
        or programme.timing_review_status != "unreviewed"
    ):
        raise RuntimeError(f"{code} review status changed without business approval")
    if code == "TLL":
        if programme.execution_mode != "advisory_sessions":
            raise RuntimeError("TLL must use advisory-session execution")
        if len(programme.session_line_ids) != 6:
            raise RuntimeError("TLL must contain exactly six advisory sessions")
        if sum(programme.session_line_ids.mapped("source_task_count")) != 12:
            raise RuntimeError("TLL session trace must reconcile all 12 legacy tasks")
        if programme.gate_line_ids or programme.dependency_rule_ids or programme.artifact_rule_ids:
            raise RuntimeError("TLL must not contain B-Series gate controls")
        print("STAGING_PROGRAMME_PASS", code, "ADVISORY_SESSIONS", 6, "LEGACY_REFERENCES", 12, "DRAFT_UNREVIEWED")
        continue
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
    if programme.execution_mode != "governed_gates":
        raise RuntimeError(f"{code} must remain gate-governed")
    if code == "LGC":
        a004 = programme.activity_line_ids.filtered(
            lambda activity: "A-004" in (activity.legacy_master_codes or "").upper()
        )[:1]
        if not a004 or a004.gate_line_id.stage_id.code != "PA-00":
            raise RuntimeError("LGC A-004 is not controlled inside Project Activation / IG-01")
    if code in {"LGC", "LGV", "TLC"}:
        weekly = programme.activity_line_ids.filtered(
            lambda activity: (activity.legacy_master_codes or "").upper()
            in {"A-026", "A-027", "A-028", "A-029", "A-030", "A-031"}
        )
        if set(weekly.mapped("legacy_master_codes")) != {
            "A-026", "A-027", "A-028", "A-029", "A-030", "A-031"
        }:
            raise RuntimeError(f"{code} does not contain six separate weekly manufacturing reports")
    for gate in programme.gate_line_ids.filtered(
        lambda item: item.stage_id.stage_type != "milestone"
    ):
        expected_gate_form = "IG-01-G01" if gate.stage_id.code == "PA-00" else "%s-G01" % gate.stage_id.code
        if not programme.artifact_rule_ids.filtered(
            lambda rule: rule.stage_id == gate.stage_id
            and rule.artifact_master_id.code == expected_gate_form
            and rule.mandatory
        ):
            raise RuntimeError(f"{code} {gate.stage_id.code} lacks its exact Gate Forms v1.9 record")
    if programme.gate_line_ids.filtered(
        lambda gate: gate.stage_id.code in {"PRE-B2", "LGD-SIGNOFF"}
        and gate.stage_id.stage_type != "milestone"
    ):
        raise RuntimeError(f"{code} treats a route milestone as a formal technical gate")
    if programme.activity_line_ids.filtered(lambda activity: activity.duration_days != 0):
        raise RuntimeError(f"{code} contains unapproved non-zero planning durations")
    if programme.activity_line_ids.filtered(
        lambda activity: activity.coordinator_designation_id.code != "PROJECT-COORD"
        or activity.authority_source_reference != SOURCE_REFERENCE
        or activity.authority_source_version != SOURCE_VERSION
    ):
        raise RuntimeError(f"{code} activity authority is not fully source-controlled")
    for activity in programme.activity_line_ids:
        master_codes = _master_codes(activity)
        unknown_codes = master_codes - set(OWNER_BY_MASTER_CODE)
        if unknown_codes:
            raise RuntimeError(
                f"{code} {activity.code} has uncontrolled master codes: {sorted(unknown_codes)}"
            )
        controlled_owners = {OWNER_BY_MASTER_CODE[item] for item in master_codes}
        if len(controlled_owners) == 1 and activity.owner_designation_id.code not in controlled_owners:
            raise RuntimeError(
                f"{code} {activity.code} owner does not match its controlled master activity"
            )
        if len(controlled_owners) > 1 and not controlled_owners.issubset(
            set(activity.support_designation_ids.mapped("code"))
        ):
            raise RuntimeError(
                f"{code} {activity.code} replacement activity does not retain all source owners"
            )
        if master_codes & ACCOUNTING_SUPPORT_CODES and (
            "ACCOUNTING-PAYMENTS" not in activity.support_designation_ids.mapped("code")
        ):
            raise RuntimeError(f"{code} {activity.code} is missing controlled accounting support")
    for master_code, expected_owner in expected_authority.items():
        activity = programme.activity_line_ids.filtered(
            lambda item: master_code in {
                value.strip().upper()
                for value in (item.legacy_master_codes or "").split(",")
                if value.strip()
            }
            or (item.name or "").upper().startswith(master_code + ":")
        )[:1]
        if activity and activity.owner_designation_id.code != expected_owner:
            raise RuntimeError(
                f"{code} {master_code} owner mismatch: "
                f"expected {expected_owner}, found {activity.owner_designation_id.code}"
            )
    commercial_milestones = programme.activity_line_ids.filtered(
        lambda activity: (activity.name or "").upper().startswith("CM-")
    )
    if commercial_milestones.filtered(
        lambda activity: activity.owner_designation_id.code != "COMMERCIAL-LOGISTICS"
        or "ACCOUNTING-PAYMENTS" not in activity.support_designation_ids.mapped("code")
    ):
        raise RuntimeError(f"{code} commercial milestones do not carry controlled finance support")
    if programme.dependency_rule_ids.filtered(
        lambda rule: rule.source_reference != "PN_CTL_Activity_Dependencies_Specification_v1.4"
    ):
        raise RuntimeError(f"{code} contains superseded dependency authority")
    a091 = programme.activity_line_ids.filtered(
        lambda activity: "A-091" in (activity.legacy_master_codes or "").upper()
    )[:1]
    if a091 and "NO ACTUAL PAYMENT" not in (a091.name or "").upper():
        raise RuntimeError(f"{code} A-091 is not clearly authorization-only")
    cm11 = programme.activity_line_ids.filtered(
        lambda activity: (activity.name or "").upper().startswith("CM-11:")
    )
    if code in {"LGC", "LGV", "TLC"}:
        if len(cm11) != 1 or "SOLE STANDARD PAYMENT EVENT" not in (cm11.name or "").upper():
            raise RuntimeError(f"{code} does not identify CM-11 as the sole actual final payment")
        b8_close = programme.activity_line_ids.filtered(
            lambda activity: "B8-09" in (activity.legacy_master_codes or "").upper()
        )[:1]
        if cm11 not in b8_close.predecessor_ids:
            raise RuntimeError(f"{code} can close before CM-11 actual final payment")
    a067 = programme.activity_line_ids.filtered(
        lambda activity: "A-067" in (activity.legacy_master_codes or "").upper()
    )[:1]
    cm07_demand = programme.activity_line_ids.filtered(
        lambda activity: (activity.name or "").upper().startswith("CM-07: DEMAND RAISED")
    )[:1]
    cm07_collected = programme.activity_line_ids.filtered(
        lambda activity: (activity.name or "").upper().startswith("CM-07: GOVERNANCE FEE COLLECTED")
    )[:1]
    if a067 and (
        not cm07_demand
        or cm07_demand.gate_line_id != a067.gate_line_id
        or a067 not in cm07_demand.predecessor_ids
        or cm07_demand not in cm07_collected.predecessor_ids
    ):
        raise RuntimeError(f"{code} CM-07 is not correctly triggered after A-067")
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
