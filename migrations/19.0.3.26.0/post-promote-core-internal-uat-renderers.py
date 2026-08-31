"""Promote core internal S-Series documents to controlled UAT generation."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env["hjig.sseries.document.template"].with_context(install_mode=True)
    authority = {
        "S4-ACCEPTANCE": {
            "source_sha256": "213e2b3fa7a050b7871445263cf7d828c0416339093f061ec3fffbe4d14cabaf",
            "expected_page_count": 1,
            "notes": "Server-only exact-native source approved for internal-UAT draft generation. Rendered visual/content QA, user final approval and any external release remain separate.",
        },
        "S5-ORDER-PUNCH": {
            "source_sha256": "6a97d8d9607409645f72496e66219aaea0e5f5063994975b1e83f43360751a78",
            "expected_page_count": 3,
            "notes": "Server-only exact-native source approved for internal-UAT draft generation. Rendered visual/content QA and execution approval remain separate.",
        },
        "S6-TEAM-HANDOVER": {
            "source_sha256": "5f024369c2e8169fa3690d3dcfaca3e66ae9e6052e9efe6fe2a051d6d4daf06e",
            "expected_page_count": 2,
            "notes": "Server-only exact-native source approved for internal-UAT draft generation. Rendered visual/content QA and B0 release approval remain separate.",
        },
    }
    for code, specific in authority.items():
        template = Template.search([("code", "=", code)], limit=1)
        if not template:
            continue
        template.write({
            **specific,
            "template_type": "BUNDLED_SERVER_ONLY_EXACT_NATIVE_DOCX",
            "authority_status": "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE",
            "approved_for_internal_uat_generation": True,
            "rendering_status": "ready",
            "template_visual_qa_verified": False,
            "template_content_qa_verified": False,
            "user_final_approval": False,
            "customer_issue_allowed": False,
            "supplier_issue_allowed": False,
        })
