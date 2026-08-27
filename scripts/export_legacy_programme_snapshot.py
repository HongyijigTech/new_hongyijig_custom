"""Run with Odoo shell against production; performs database reads only."""

import hashlib
import json
import os
import re


EXPECTED = {1: 141, 2: 22, 3: 127, 4: 106, 5: 12}
OUTPUT_PATH = os.environ.get(
    "HJIG_PROGRAMME_SNAPSHOT_PATH", "/tmp/hjig_programme_legacy_snapshot.json"
)

if env.cr.dbname != "hongyijig_30April_db":
    raise RuntimeError("Legacy export is permitted only from hongyijig_30April_db")

records = env["project.task"].with_context(active_test=False).search(
    [("project_id", "in", list(EXPECTED))],
    order="project_id, stage_id, sequence, id",
)
master_code_pattern = re.compile(r"\b(?:A-\d{3}[a-z]?|B8-\d{2})\b", re.IGNORECASE)


def activity_master_codes(task_name):
    name = (task_name or "").strip()
    if not master_code_pattern.match(name):
        return []
    return [code.upper() for code in master_code_pattern.findall(name.split(":", 1)[0])]


Master = env["x_activity_master"].with_context(active_test=False)
masters = Master.search([], order="id")
master_by_id = {master.id: master for master in masters}
rules = env["x_activity_dependency_rule"].with_context(active_test=False).search(
    [("x_rule_status", "=", "active")], order="id"
)
payload = {
    "source_database": env.cr.dbname,
    "projects": {},
    "activity_masters": [
        {
            "id": master.id,
            "code": master.x_activity_code,
            "name": master.x_activity_name,
            "basis": master.x_activity_basis,
            "conditional": master.x_is_conditional,
            "owner_role": master.x_owner_role,
            "stage_gate": master.x_stage_gate,
            "master_status": master.x_master_status,
            "source_reference": master.x_source_reference,
            "source_version": master.x_source_version,
        }
        for master in masters
    ],
    "dependency_rules": [
        {
            "id": rule.id,
            "predecessor_master_code": master_by_id[rule.x_predecessor_master_id.id].x_activity_code,
            "successor_master_code": master_by_id[rule.x_successor_master_id.id].x_activity_code,
            "predecessor_basis": rule.x_predecessor_basis,
            "successor_basis": rule.x_successor_basis,
            "rule_type": rule.x_rule_type,
            "scope_matching_rule": rule.x_scope_matching_rule,
            "aggregation_requirement": rule.x_aggregation_requirement,
            "conditional_handling": rule.x_conditional_handling,
            "source_reference": rule.x_source_reference,
            "source_version": rule.x_source_version,
            "applicable_programmes": [
                code for code, enabled in (
                    ("LGC", rule.x_appl_complete),
                    ("LGD", rule.x_appl_design),
                    ("LGV", rule.x_appl_development),
                    ("TLC", rule.x_appl_toollock_control),
                    ("TLL", rule.x_appl_toollock_lite),
                ) if enabled
            ],
        }
        for rule in rules
    ],
}
for project_id, expected_count in EXPECTED.items():
    tasks = records.filtered(lambda task: task.project_id.id == project_id)
    if len(tasks) != expected_count:
        raise RuntimeError(
            "Project %s task count is %s; expected %s" % (project_id, len(tasks), expected_count)
        )
    payload["projects"][str(project_id)] = [
        {
            "id": task.id,
            "name": task.name,
            "stage_id": task.stage_id.id,
            "stage_name": task.stage_id.name,
            "sequence": task.sequence,
            "active": task.active,
            "activity_master_codes": activity_master_codes(task.name),
        }
        for task in tasks
    ]

encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
with open(OUTPUT_PATH, "wb") as snapshot:
    snapshot.write(encoded)
print("SNAPSHOT_PATH", OUTPUT_PATH)
print("SNAPSHOT_SHA256", hashlib.sha256(encoded).hexdigest())
print("SNAPSHOT_TASK_COUNT", sum(len(tasks) for tasks in payload["projects"].values()))
print("SNAPSHOT_MASTER_COUNT", len(payload["activity_masters"]))
print("SNAPSHOT_DEPENDENCY_RULE_COUNT", len(payload["dependency_rules"]))
