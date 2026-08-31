"""Reconcile non-generated payment, accounting and B0 evidence statuses."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Case = env["hjig.sseries.case"]

    for case in Case.search([]):
        evidence = {
            "S5-PAYMENT-EVIDENCE": case.payment_evidence_reference,
            "S5-TAX-INVOICE": case.tax_invoice_reference,
        }
        if case.b0_manifest_id:
            evidence["B0-HANDOVER-MANIFEST"] = case.b0_manifest_id.name

        for code, reference in evidence.items():
            reference = (reference or "").strip()
            if not reference:
                continue
            artifact = case.artifact_ids.filtered(lambda item, value=code: item.code == value)[:1]
            if not artifact or artifact.state in ("approved", "issued"):
                continue
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "state": "evidence_recorded",
                "issue_reference": reference,
                "customer_issue_allowed": False,
                "supplier_issue_allowed": False,
            })
