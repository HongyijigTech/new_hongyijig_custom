"""Run with Odoo shell against staging to create unapproved draft DNA."""

import json
import os
import re


INPUT_PATH = os.environ.get(
    "HJIG_PROGRAMME_SNAPSHOT_PATH", "/tmp/hjig_programme_legacy_snapshot.json"
)
PROGRAMMES = {
    1: ("LGC", 141),
    2: ("LGD", 22),
    3: ("LGV", 127),
    4: ("TLC", 106),
    5: ("TLL", 12),
}


def canonical_stage(stage_name):
    upper = (stage_name or "").upper()
    if "SESSION" in upper:
        match = re.search(r"SESSION\s*(\d+)", upper)
        if match:
            return "TLL-S%02d" % int(match.group(1))
    if "PRE-B2" in upper:
        return "PRE-B2"
    if "TG-10-LITE" in upper:
        return "TG-10-LITE"
    match = re.search(r"TG-(\d{2})", upper)
    if match:
        return "TG-%s" % match.group(1)
    if "IG-01" in upper or "PROJECT PLANNING" in upper:
        return "PA-00"
    if "DESIGN ONLY" in upper:
        return "TG-01"
    raise RuntimeError("No canonical gate mapping for legacy stage: %s" % stage_name)


def designations_for(stage_code, activity_name):
    upper = (activity_name or "").upper()
    if stage_code == "PA-00":
        return "PROJECT-COORD", "PROJECT-MANAGER"
    if stage_code == "TG-01":
        if any(word in upper for word in ("TOOLMAKER", "COMMERCIAL", "SUPPLIER")):
            return "PROJECT-MANAGER", "PMO-DOC"
        return "SR-PRODUCT-DESIGN", "PROJECT-MANAGER"
    if stage_code == "PRE-B2":
        return "PROJECT-MANAGER", "PMO-DOC"
    if stage_code == "TG-02":
        return "SR-TOOL-DESIGN", "PROJECT-MANAGER"
    if stage_code == "TG-03":
        return "SR-TOOL-DEVELOPMENT", "PROJECT-MANAGER"
    if stage_code in ("TG-04", "TG-05", "TG-06"):
        if any(word in upper for word in ("INSPECTION", "DIMENSION", "VISUAL", "ASSEMBLY", "QUALITY")):
            return "QUALITY-INSPECTION", "PROJECT-MANAGER"
        return "PROJECT-ENGINEER", "PROJECT-MANAGER"
    if stage_code in ("TG-07", "TG-08"):
        return "COMMERCIAL-LOGISTICS", "PROJECT-MANAGER"
    if stage_code == "TG-09":
        return "PROJECT-ENGINEER", "CUSTOMER-APPROVER"
    if stage_code in ("TG-10", "TG-10-LITE"):
        return "PROJECT-MANAGER", "PMO-DOC"
    if stage_code.startswith("TLL-S"):
        return "PROJECT-ENGINEER", "PROJECT-MANAGER"
    raise RuntimeError("No designation rule for canonical stage %s" % stage_code)


if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("Draft import is permitted only in HongyijigTech_10Feb staging")

with open(INPUT_PATH, "r", encoding="utf-8") as snapshot:
    payload = json.load(snapshot)
if payload.get("source_database") != "hongyijig_30April_db":
    raise RuntimeError("Snapshot source database is not the verified production database")

Stage = env["hjig.launchguard.stage"]
Designation = env["hjig.governance.designation"]
Version = env["hjig.programme.template.version"]
Gate = env["hjig.programme.template.gate"]
Activity = env["hjig.programme.template.activity"]
ArtifactRule = env["hjig.programme.template.artifact"]
Artifact = env["hjig.governance.artifact.master"]
DependencyRule = env["hjig.programme.template.dependency.rule"]

stage_by_code = {stage.code: stage for stage in Stage.search([])}
designation_by_code = {designation.code: designation for designation in Designation.search([])}
master_by_code = {
    master["code"].upper(): master for master in payload.get("activity_masters", [])
}


def sync_artifact_rules(version):
    existing = {
        (rule.stage_id.id, rule.artifact_master_id.id)
        for rule in version.artifact_rule_ids
    }
    for gate in version.gate_line_ids:
        artifacts = Artifact.search([("applicable_stage_ids", "in", gate.stage_id.id)])
        for artifact in artifacts:
            key = (gate.stage_id.id, artifact.id)
            if key not in existing:
                ArtifactRule.create({
                    "version_id": version.id,
                    "artifact_master_id": artifact.id,
                    "stage_id": gate.stage_id.id,
                    "mandatory": True,
                })
                existing.add(key)


def sync_dependency_rules(version, programme_code, task_payload_by_id):
    activity_by_master_code = {}
    for activity in version.activity_line_ids:
        source = task_payload_by_id[activity.legacy_source_task_id]
        codes = [code.upper() for code in source.get("activity_master_codes", [])]
        values = {"legacy_master_codes": ",".join(codes) or False}
        if codes:
            master = master_by_code.get(codes[0], {})
            values.update({
                "execution_basis": master.get("basis") or "project",
                "conditional": bool(master.get("conditional")),
            })
        activity.write(values)
        for code in codes:
            if code in activity_by_master_code and activity_by_master_code[code] != activity:
                raise RuntimeError("Duplicate Activity Master code %s in %s" % (code, programme_code))
            activity_by_master_code[code] = activity

    applicable = [
        rule for rule in payload.get("dependency_rules", [])
        if programme_code in rule.get("applicable_programmes", [])
    ]
    expected_source_ids = set()

    def upsert_rule(source_rule_id, predecessor, successor, values):
        existing = DependencyRule.search([
            ("version_id", "=", version.id),
            ("legacy_source_rule_id", "=", source_rule_id),
        ], limit=1)
        rule_values = {
            "version_id": version.id,
            "legacy_source_rule_id": source_rule_id,
            "predecessor_activity_id": predecessor.id,
            "successor_activity_id": successor.id,
        }
        rule_values.update(values)
        if existing:
            existing.write(rule_values)
        else:
            DependencyRule.create(rule_values)
        if predecessor not in successor.predecessor_ids:
            successor.predecessor_ids = [(4, predecessor.id)]
        expected_source_ids.add(source_rule_id)

    unmapped = []
    for source_rule in applicable:
        predecessor = activity_by_master_code.get(source_rule["predecessor_master_code"].upper())
        successor = activity_by_master_code.get(source_rule["successor_master_code"].upper())
        if not predecessor or not successor:
            unmapped.append(source_rule["id"])
            continue
        upsert_rule(source_rule["id"], predecessor, successor, {
            "predecessor_basis": source_rule["predecessor_basis"],
            "successor_basis": source_rule["successor_basis"],
            "rule_type": source_rule["rule_type"],
            "scope_matching_rule": source_rule["scope_matching_rule"],
            "aggregation_requirement": source_rule["aggregation_requirement"],
            "conditional_handling": source_rule.get("conditional_handling"),
            "source_reference": source_rule.get("source_reference"),
            "source_version": source_rule.get("source_version"),
        })
    if unmapped:
        raise RuntimeError(
            "%s dependency rules do not map to route activities: %s"
            % (programme_code, ",".join(map(str, unmapped)))
        )
    # Gate barriers are derived from the verified route itself. Every activity in a
    # later gate waits for every activity in the immediately preceding gate, while
    # the 34 source rules retain the component/mould aggregation semantics inside gates.
    barrier_source_id = -1
    ordered_gates = version.gate_line_ids.filtered("required").sorted("sequence")
    for previous_gate, current_gate in zip(ordered_gates, ordered_gates[1:]):
        predecessors = version.activity_line_ids.filtered(
            lambda activity: activity.gate_line_id == previous_gate
        ).sorted("sequence")
        successors = version.activity_line_ids.filtered(
            lambda activity: activity.gate_line_id == current_gate
        ).sorted("sequence")
        for predecessor in predecessors:
            for successor in successors:
                upsert_rule(barrier_source_id, predecessor, successor, {
                    "predecessor_basis": "project",
                    "successor_basis": "project",
                    "rule_type": "gate_barrier",
                    "scope_matching_rule": "PROJECT->PROJECT (same programme run)",
                    "aggregation_requirement": "All activities in the immediately preceding gate must complete.",
                    "conditional_handling": "Gate barrier; conditional activities require approved disposition.",
                    "source_reference": "Verified legacy programme stage route",
                    "source_version": payload.get("snapshot_sha256") or "snapshot",
                })
                barrier_source_id -= 1
    stale = version.dependency_rule_ids.filtered(
        lambda rule: rule.legacy_source_rule_id not in expected_source_ids
    )
    if stale:
        stale.unlink()
    if len(version.dependency_rule_ids) != len(expected_source_ids):
        raise RuntimeError("%s dependency rule count does not reconcile" % programme_code)
    return len(applicable), len(expected_source_ids) - len(applicable)

for project_id, (programme_code, expected_count) in PROGRAMMES.items():
    tasks = payload["projects"].get(str(project_id), [])
    task_payload_by_id = {task["id"]: task for task in tasks}
    if len(tasks) != expected_count:
        raise RuntimeError("Snapshot count mismatch for Project %s" % project_id)
    template = env["hjig.programme.template"].search([("code", "=", programme_code)], limit=1)
    if not template:
        raise RuntimeError("Missing programme template %s" % programme_code)
    version = Version.search(
        [("template_id", "=", template.id), ("version", "=", "1.0")], limit=1
    )
    if version and version.activity_line_ids:
        source_ids = set(version.activity_line_ids.mapped("legacy_source_task_id"))
        expected_ids = {task["id"] for task in tasks}
        if source_ids != expected_ids:
            raise RuntimeError("Existing %s v1.0 draft does not reconcile to source" % programme_code)
        sync_artifact_rules(version)
        dependency_count, barrier_count = sync_dependency_rules(
            version, programme_code, task_payload_by_id
        )
        print(
            "PROGRAMME_ALREADY_RECONCILED",
            programme_code,
            len(source_ids),
            len(version.artifact_rule_ids),
            dependency_count,
            barrier_count,
        )
        continue
    values = {
        "legacy_source_database": payload["source_database"],
        "legacy_source_project_id": project_id,
        "legacy_source_task_count": expected_count,
        # These stay unreviewed until the business-approved dependency and evidence
        # maps have been reconciled. Draft import must never self-approve governance.
        "dependency_review_status": "unreviewed",
        "evidence_review_status": "unreviewed",
    }
    if not version:
        values.update({"template_id": template.id, "version": "1.0"})
        version = Version.create(values)
    else:
        version.write(values)

    gate_by_code = {}
    ordered_stage_codes = []
    for task in tasks:
        code = canonical_stage(task["stage_name"])
        if code not in ordered_stage_codes:
            ordered_stage_codes.append(code)
    for sequence, code in enumerate(ordered_stage_codes, start=1):
        stage = stage_by_code.get(code)
        if not stage:
            raise RuntimeError("Missing canonical staging gate %s" % code)
        gate_by_code[code] = Gate.create({
            "version_id": version.id,
            "stage_id": stage.id,
            "sequence": sequence * 10,
            "closure_variant": "lite" if code == "TG-10-LITE" else "standard",
        })

    for index, task in enumerate(tasks, start=1):
        stage_code = canonical_stage(task["stage_name"])
        owner_code, approver_code = designations_for(stage_code, task["name"])
        owner = designation_by_code.get(owner_code)
        approver = designation_by_code.get(approver_code)
        if not owner or not approver:
            raise RuntimeError("Missing designation %s/%s" % (owner_code, approver_code))
        Activity.create({
            "version_id": version.id,
            "code": "%s-A%03d" % (programme_code, index),
            "name": task["name"],
            "sequence": index * 10,
            "gate_line_id": gate_by_code[stage_code].id,
            "owner_designation_id": owner.id,
            "approver_designation_id": approver.id,
            "duration_days": 1,
            "legacy_source_task_id": task["id"],
            "legacy_source_stage_id": task["stage_id"],
            "legacy_source_stage_name": task["stage_name"],
            "legacy_master_codes": ",".join(task.get("activity_master_codes", [])) or False,
        })

    sync_artifact_rules(version)
    dependency_count, barrier_count = sync_dependency_rules(
        version, programme_code, task_payload_by_id
    )
    print(
        "PROGRAMME_RECONCILED",
        programme_code,
        len(version.gate_line_ids),
        len(version.activity_line_ids),
        len(version.artifact_rule_ids),
        dependency_count,
        barrier_count,
        version.state,
    )

env.cr.commit()
print("DRAFT_IMPORT_COMPLETE_COMMITTED")
