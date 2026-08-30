"""Reconcile Draft programme authority and commercial controls idempotently."""

from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    risk_master = env["hjig.governance.artifact.master"].search([
        ("code", "=", "FRM-006"),
    ], limit=1)
    if not risk_master:
        raise ValidationError("Controlled Risk Register master FRM-006 is missing.")
    if risk_master.owner_designation_id == risk_master.approver_designation_id:
        raise ValidationError("FRM-006 must segregate its owner and approver designations.")

    versions = env["hjig.programme.template.version"].search([
        ("state", "=", "draft"),
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC"]),
    ])
    changed_versions = env["hjig.programme.template.version"]
    for activity in versions.mapped("activity_line_ids").filtered(
        lambda item: (item.name or "").upper().startswith("A-005:")
        and risk_master in item.required_artifact_ids
        and item.owner_designation_id == item.approver_designation_id
    ):
        activity.write({
            "owner_designation_id": risk_master.owner_designation_id.id,
            "approver_designation_id": risk_master.approver_designation_id.id,
        })
        changed_versions |= activity.version_id

    commercial_changed_versions = env["hjig.programme.template.version"]
    for activity in versions.mapped("activity_line_ids").filtered(
        lambda item: (item.name or "").upper().startswith("CM-")
    ):
        commercial_values = activity._hjig_commercial_rule_defaults()
        if any(activity[field_name] != value for field_name, value in commercial_values.items()):
            activity.write(commercial_values)
            commercial_changed_versions |= activity.version_id

    changed_versions |= commercial_changed_versions

    if changed_versions:
        changed_versions.with_context(hjig_programme_review_control=True).write({
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

    if commercial_changed_versions:
        env["project.task"].search([
            ("hjig_template_activity_id.version_id", "in", commercial_changed_versions.ids),
        ])._hjig_sync_commercial_rule_from_template()
