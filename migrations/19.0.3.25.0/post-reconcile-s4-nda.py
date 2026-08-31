"""Reconcile the fail-closed reusable S4 NDA registry candidate."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env["hjig.sseries.document.template"].with_context(
        install_mode=True
    ).search([("code", "=", "S4-NDA")], limit=1)
    if not template:
        return

    template.write({
        "name": "Confidentiality, Non-Solicitation and Introduced-Party Protection Agreement",
        "master_file_id": "LOCAL-S4-NDA-REUSABLE-ODOO-MASTER-R1",
        "source_sha256": "cdccee7ebe36c160e44a03b38281ead11f180c02284affab9b1bfc2ea1e093a9",
        "template_type": "BUNDLED_INTERNAL_UAT_DOCX_WITH_HELVETICA_PDF_EVIDENCE",
        "expected_page_count": 4,
        "authority_status": "REUSABLE_INTERNAL_UAT_USER_AND_LEGAL_APPROVAL_PENDING",
        "rendering_status": "blocked",
        "approved_for_internal_uat_generation": False,
        "template_visual_qa_verified": False,
        "template_content_qa_verified": False,
        "user_final_approval": False,
        "customer_issue_allowed": False,
        "supplier_issue_allowed": False,
        "notes": (
            "Customer-neutral reusable internal-UAT master is bundled for audit. "
            "Sixteen controlled renderer tokens, completed-fact render QA, explicit "
            "user final approval and India-qualified legal approval remain mandatory; "
            "generation and customer issue stay disabled."
        ),
    })
