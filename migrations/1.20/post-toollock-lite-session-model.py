# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


SESSIONS = (
    ("TLL-S01", 10, "SOR + BOP Collection Advisory", "1 full day", "FRM-TLL-001"),
    ("TLL-S02", 20, "RFQ Framework Advisory", "Half day", "FRM-TLL-002"),
    ("TLL-S03", 30, "Supplier Selection Methodology Advisory", "Half day", "FRM-TLL-003"),
    ("TLL-S04", 40, "Pre-Tooling Governance Advisory", "Half day", "FRM-TLL-004"),
    ("TLL-S05", 50, "Trial Sign-Off Advisory", "Half day", "FRM-TLL-005"),
    ("TLL-S06", 60, "Dispatch Readiness Advisory", "Half day", "FRM-TLL-006"),
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env["hjig.programme.template"].search([("code", "=", "TLL")], limit=1)
    if not template:
        return
    runs = env["hjig.programme.run"].search_count([("template_version_id.template_id", "=", template.id)])
    if runs:
        raise RuntimeError("ToolLock Lite migration stopped: programme runs already exist")
    versions = template.version_ids
    if versions.filtered(lambda item: item.state != "draft"):
        raise RuntimeError("ToolLock Lite migration stopped: only draft versions may be reconciled")

    template.write({
        "execution_mode": "advisory_sessions",
        "description": "Six-session advisory programme; no B-Series gates or execution monitoring. Legacy source: Project 5.",
    })
    Session = env["hjig.programme.template.session"]
    Artifact = env["hjig.governance.artifact.master"]
    Stage = env["hjig.launchguard.stage"]
    for programme in versions:
        grouped_ids = {}
        for activity in programme.activity_line_ids.sorted(lambda item: (item.gate_line_id.sequence, item.sequence, item.id)):
            stage_code = activity.gate_line_id.stage_id.code
            grouped_ids.setdefault(stage_code, []).append(activity.legacy_source_task_id)

        programme.dependency_rule_ids.unlink()
        programme.checklist_item_ids.unlink()
        programme.artifact_rule_ids.unlink()
        programme.activity_line_ids.unlink()
        programme.gate_line_ids.unlink()
        programme.session_line_ids.unlink()

        for code, sequence, name, duration, artifact_code in SESSIONS:
            source_ids = [source_id for source_id in grouped_ids.get(code, []) if source_id]
            if len(source_ids) != 2:
                raise RuntimeError("%s must reconcile exactly two legacy task references" % code)
            artifact = Artifact.search([("code", "=", artifact_code)], limit=1)
            stage = Stage.search([("code", "=", code)], limit=1)
            if not artifact:
                raise RuntimeError("Missing governed ToolLock Lite framework %s" % artifact_code)
            if not stage:
                raise RuntimeError("Missing governed ToolLock Lite stage %s" % code)
            Session.create({
                "version_id": programme.id,
                "code": code,
                "sequence": sequence,
                "name": name,
                "indicative_duration": duration,
                "stage_id": stage.id,
                "owner_designation_id": artifact.owner_designation_id.id,
                "approver_designation_id": artifact.approver_designation_id.id,
                "framework_artifact_id": artifact.id,
                "legacy_source_task_ids": ",".join(str(item) for item in source_ids),
                "source_task_count": len(source_ids),
                "source_reference": "Hongyi_BSeries_Constitution_v2_5_v6_9",
                "source_version": "v6.9",
                "advisory_scope": "Advisory review using a blank controlled framework; tooling execution monitoring and filled proprietary templates are outside scope.",
            })

    env["hjig.programme.template.version"].search([
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC"]),
        ("state", "=", "draft"),
    ])._sync_authoritative_gate_checklists()
