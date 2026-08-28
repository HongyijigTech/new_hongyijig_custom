"""Apply Founder-approved dependency v1.4 and B8 references to draft DNA."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Version = env["hjig.programme.template.version"]
    drafts = Version.search([
        ("state", "=", "draft"),
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC", "TLL"]),
    ])
    for programme in drafts:
        if programme.execution_mode == "governed_gates":
            # Version 1.26 imported one day as a technical placeholder.  No
            # controlled source supports that promise, so restore an explicit
            # unbaselined zero before governed timing review.
            programme.activity_line_ids.filtered(
                lambda activity: activity.legacy_source_task_id and activity.duration_days == 1
            ).write({"duration_days": 0})
            programme._sync_founder_approved_dependency_rules()
            programme._sync_authoritative_gate_checklists()
        else:
            programme.session_line_ids.write({
                "source_reference": "Hongyi_BSeries_Constitution_v2_5_v6_11",
                "source_version": "v6.11 / Founder approved 21-Aug-2026",
            })
        programme.write({
            "dependency_review_status": "unreviewed",
            "evidence_review_status": "unreviewed",
            "timing_review_status": "unreviewed",
        })
