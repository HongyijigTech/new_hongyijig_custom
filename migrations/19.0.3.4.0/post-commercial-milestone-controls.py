"""Bind CM activities to existing verified commercial records without duplicating ledgers."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    versions = env["hjig.programme.template.version"].search([
        ("state", "=", "draft"),
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC"]),
    ])
    for programme in versions:
        for activity in programme.activity_line_ids:
            activity.write(activity._hjig_commercial_rule_defaults())
        programme.with_context(hjig_programme_review_control=True).write({
            "evidence_review_status": "unreviewed",
            "evidence_reviewed_by_id": False,
            "evidence_reviewed_on": False,
        })
    env["project.task"].search([
        ("hjig_template_activity_id", "!=", False),
    ])._hjig_sync_commercial_rule_from_template()
