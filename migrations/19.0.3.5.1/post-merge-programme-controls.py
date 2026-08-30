"""Merge Founder-approved activity authority with commercial milestone controls."""

from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    versions = env["hjig.programme.template.version"].search([
        ("state", "=", "draft"),
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC", "TLL"]),
    ])
    if len(versions) != 5:
        raise ValidationError("Exactly five Draft B-Series programme versions are required.")

    risk_master = env["hjig.governance.artifact.master"].search([
        ("code", "=", "FRM-006"),
    ], limit=1)
    if not risk_master:
        raise ValidationError("Controlled Risk Register master FRM-006 is missing.")
    if (
        risk_master.owner_designation_id.code != "PROJECT-MANAGER"
        or risk_master.approver_designation_id.code != "PMO-DOC"
    ):
        raise ValidationError("FRM-006 must use Project Manager owner and PMO Document Controller approval.")

    versions._sync_founder_approved_activity_authority()

    commercial_versions = versions.filtered(lambda item: item.execution_mode == "governed_gates")
    for activity in commercial_versions.mapped("activity_line_ids").filtered(
        lambda item: (item.name or "").upper().startswith("CM-")
    ):
        activity.write(activity._hjig_commercial_rule_defaults())

    versions.with_context(hjig_programme_review_control=True).write({
        "dependency_review_status": "unreviewed",
        "dependency_reviewed_by_id": False,
        "dependency_reviewed_on": False,
        "evidence_review_status": "unreviewed",
        "evidence_reviewed_by_id": False,
        "evidence_reviewed_on": False,
        "timing_review_status": "unreviewed",
        "timing_reviewed_by_id": False,
        "timing_reviewed_on": False,
    })

    env["project.task"].search([
        ("hjig_template_activity_id.version_id", "in", commercial_versions.ids),
    ])._hjig_sync_commercial_rule_from_template()
