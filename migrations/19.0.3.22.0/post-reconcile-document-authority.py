"""Reconcile Odoo document authority with the locked visual registries."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env["hjig.sseries.document.template"].with_context(install_mode=True)

    for code in (
        "LGC-03", "LGD-03", "LGV-03", "TLC-03", "TLL-03", "SB-03", "PG-03", "PB-SB-03",
    ):
        Template.search([("code", "=", code)], limit=1).write({
            "template_content_qa_verified": True,
        })

    authority = {
        "S4-ACCEPTANCE": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 1,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Candidate only; exact visual-parent approval and Helvetica-bound rendered QA remain pending.",
        },
        "S4-NDA": {
            "name": "Confidentiality, Non-Solicitation and Introduced-Party Protection Agreement",
            "master_file_id": "1UphqzbhrtxgCBqAAY_LfmbQjnJIbciFw",
            "authority_status": "CLAUDE_DESIGN_INTERNAL_UAT_USER_APPROVAL_PENDING",
            "template_type": "WORD_DOCX_ARCHIVE",
            "expected_page_count": 4,
            "rendering_status": "blocked",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Internal-UAT legal candidate only; exact facts, user approval and India-qualified legal-counsel approval remain mandatory.",
        },
        "S5-ORDER-PUNCH": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 3,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Candidate only; token consolidation, visual-parent approval and rendered QA remain pending.",
        },
        "S5-PROFORMA": {
            "name": "System-Generated Proforma Invoice",
            "master_file_id": "1IIs9UYQ782mQzoS1Fy2g_nySl10-0YvTy4YMB0UV9Qs",
            "authority_status": "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 2,
            "rendering_status": "ready",
            "approved_for_internal_uat_generation": True,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Internal-UAT generation authority only. Finance approval and customer issue remain separate; never represent as final GST invoice.",
        },
        "S5-PAYMENT-EVIDENCE": {
            "name": "Payment Receipt / Bank Evidence Record",
            "master_file_id": False,
            "authority_status": "MISSING_APPROVED_MASTER_FAIL_CLOSED",
            "template_type": "MISSING_MASTER",
            "expected_page_count": 1,
            "rendering_status": "blocked",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Payment evidence reference may be recorded, but no generated document is authorised until an exact master is approved.",
        },
        "S5-TAX-INVOICE": {
            "master_file_id": False,
            "authority_status": "DEFERRED_UNTIL_TALLY_MAPPING_APPROVAL_AND_TESTING",
            "template_type": "TALLY_E_INVOICE_DEFERRED",
            "expected_page_count": 0,
            "rendering_status": "blocked",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Blocked until accounting/Tally GST, IRN/QR and Finance authority are integrated; no fabricated issue event is permitted.",
        },
        "S6-TEAM-HANDOVER": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 2,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Candidate only; exact visual-parent approval and rendered QA remain pending.",
        },
        "S6-CHINA-HANDOVER": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 2,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Restricted internal sourcing candidate; UAT boundary, access control, visual parent and Helvetica QA remain pending.",
        },
        "S6-SUPPLIER-RFQ-EN": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 2,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Supplier-facing candidate; visual parent, UAT boundary and Helvetica QA remain pending.",
        },
        "S6-SUPPLIER-RFQ-ZH": {
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_DOCS_TEMPLATE",
            "expected_page_count": 2,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "No approved rendered Chinese RFQ exists; English semantic lock and bilingual parity QA are pending.",
        },
        "B0-HANDOVER-MANIFEST": {
            "master_file_id": "1iOmuJd_NOrr_YA7X6BOCSlnTDcf1aPyrErhTjJYSt9U",
            "authority_status": "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING",
            "template_type": "GOOGLE_SHEETS_TEMPLATE",
            "expected_page_count": 1,
            "rendering_status": "template_state",
            "approved_for_internal_uat_generation": False,
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "notes": "Controlled manifest model exists; PDF visual authority and user approval remain pending.",
        },
    }
    for code, values in authority.items():
        template = Template.search([("code", "=", code)], limit=1)
        if template:
            template.write({
                **values,
                "user_final_approval": False,
                "customer_issue_allowed": False,
                "supplier_issue_allowed": False,
            })

