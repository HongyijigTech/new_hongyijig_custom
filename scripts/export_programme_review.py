"""Export the staging B-Series definitions for evidence reconciliation."""

import json
import os


if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("This export is restricted to HongyijigTech_10Feb staging")

output_path = os.environ.get("HJIG_PROGRAMME_REVIEW_PATH", "/tmp/hjig_programme_review.json")
Version = env["hjig.programme.template.version"]
versions = Version.search([("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC", "TLL"])])

payload = {
    "database": env.cr.dbname,
    "programmes": [],
}
for version in versions.sorted(lambda item: item.template_id.code):
    programme = {
        "code": version.template_id.code,
        "name": version.template_id.name,
        "version": version.version,
        "state": version.state,
        "dependency_review_status": version.dependency_review_status,
        "evidence_review_status": version.evidence_review_status,
        "gates": [],
        "activities": [],
        "dependency_rules": [],
        "artifact_rules": [],
    }
    for gate in version.gate_line_ids.sorted("sequence"):
        programme["gates"].append({
            "sequence": gate.sequence,
            "stage_code": gate.stage_id.code,
            "stage_name": gate.stage_id.name,
            "required": gate.required,
            "closure_variant": gate.closure_variant,
        })
    for activity in version.activity_line_ids.sorted(lambda item: (item.sequence, item.code)):
        programme["activities"].append({
            "code": activity.code,
            "name": activity.name,
            "sequence": activity.sequence,
            "stage_code": activity.gate_line_id.stage_id.code,
            "owner_designation": activity.owner_designation_id.code,
            "approver_designation": activity.approver_designation_id.code,
            "execution_basis": activity.execution_basis,
            "conditional": activity.conditional,
            "predecessors": activity.predecessor_ids.mapped("code"),
            "required_artifacts": activity.required_artifact_ids.mapped("code"),
            "legacy_source_task_id": activity.legacy_source_task_id,
            "legacy_master_codes": activity.legacy_master_codes,
        })
    for rule in version.dependency_rule_ids.sorted("id"):
        programme["dependency_rules"].append({
            "legacy_source_rule_id": rule.legacy_source_rule_id,
            "predecessor": rule.predecessor_activity_id.code,
            "successor": rule.successor_activity_id.code,
            "predecessor_basis": rule.predecessor_basis,
            "successor_basis": rule.successor_basis,
            "rule_type": rule.rule_type,
            "scope_matching_rule": rule.scope_matching_rule,
            "aggregation_requirement": rule.aggregation_requirement,
            "conditional_handling": rule.conditional_handling,
            "source_reference": rule.source_reference,
            "source_version": rule.source_version,
        })
    for rule in version.artifact_rule_ids.sorted(lambda item: (item.stage_id.sequence, item.artifact_master_id.code)):
        artifact = rule.artifact_master_id
        programme["artifact_rules"].append({
            "stage_code": rule.stage_id.code,
            "artifact_code": artifact.code,
            "artifact_name": artifact.name,
            "artifact_type": artifact.artifact_type,
            "mandatory": rule.mandatory,
            "revision": artifact.revision,
            "register_type": artifact.default_register_type,
            "document_class": artifact.default_document_class,
        })
    payload["programmes"].append(programme)

with open(output_path, "w", encoding="utf-8") as review_file:
    json.dump(payload, review_file, indent=2, ensure_ascii=False)

env.cr.rollback()
print("PROGRAMME_REVIEW_EXPORT_COMPLETE", output_path, len(payload["programmes"]))
