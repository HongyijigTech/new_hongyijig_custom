import hashlib
from pathlib import Path

from odoo.tests.common import TransactionCase


class TestSSeriesDocumentAuthority(TransactionCase):
    def test_activation_registry_is_fail_closed_and_complete(self):
        Template = self.env["hjig.sseries.document.template"]
        self.assertEqual(Template.search_count([]), 24)

        expected = {
            "S4-NDA": ("blocked", False, "REUSABLE_INTERNAL_UAT_USER_AND_LEGAL_APPROVAL_PENDING"),
            "S4-INTRODUCED-PARTY-NOTICE": ("blocked", False, "CLAUDE_DESIGN_INTERNAL_UAT_USER_APPROVAL_PENDING"),
            "S4-DIRECT-ENGAGEMENT-CONSENT": ("blocked", False, "CLAUDE_DESIGN_INTERNAL_UAT_USER_APPROVAL_PENDING"),
            "S4-ACCEPTANCE": ("ready", True, "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE"),
            "S5-ORDER-PUNCH": ("ready", True, "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE"),
            "S5-PROFORMA": ("ready", True, "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE"),
            "S5-PAYMENT-EVIDENCE": ("blocked", False, "MISSING_APPROVED_MASTER_FAIL_CLOSED"),
            "S5-TAX-INVOICE": ("blocked", False, "DEFERRED_UNTIL_TALLY_MAPPING_APPROVAL_AND_TESTING"),
            "S6-TEAM-HANDOVER": ("ready", True, "APPROVED_INTERNAL_UAT_GENERATOR_TEMPLATE_CUSTOMER_RELEASE_SEPARATE"),
            "S6-CHINA-HANDOVER": ("template_state", False, "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING"),
            "S6-SUPPLIER-RFQ-EN": ("template_state", False, "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING"),
            "S6-SUPPLIER-RFQ-ZH": ("template_state", False, "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING"),
            "B0-HANDOVER-MANIFEST": ("template_state", False, "EXACT_NATIVE_CANDIDATE_USER_APPROVAL_PENDING"),
        }
        records = Template.search([("code", "in", list(expected))])
        self.assertEqual(set(records.mapped("code")), set(expected))
        for record in records:
            rendering, internal_generation, authority = expected[record.code]
            self.assertEqual(record.rendering_status, rendering)
            self.assertEqual(record.approved_for_internal_uat_generation, internal_generation)
            self.assertEqual(record.authority_status, authority)
            self.assertFalse(record.user_final_approval)
            self.assertFalse(record.customer_issue_allowed)
            self.assertFalse(record.supplier_issue_allowed)

        approved = records.filtered("approved_for_internal_uat_generation")
        self.assertEqual(
            set(approved.mapped("code")),
            {"S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S5-PROFORMA", "S6-TEAM-HANDOVER"},
        )
        self.assertFalse(approved.filtered("template_visual_qa_verified"))
        self.assertFalse(approved.filtered("template_content_qa_verified"))

        resource_root = (
            Path(__file__).resolve().parents[1]
            / "resources" / "sseries_internal_uat" / "activation_handover_r1"
        )
        governed_sources = {
            "Hongyi_S4_Acceptance_Record_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx":
                "213e2b3fa7a050b7871445263cf7d828c0416339093f061ec3fffbe4d14cabaf",
            "Hongyi_S5_Order_Punch_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx":
                "6a97d8d9607409645f72496e66219aaea0e5f5063994975b1e83f43360751a78",
            "Hongyi_S6_Team_Handover_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx":
                "5f024369c2e8169fa3690d3dcfaca3e66ae9e6052e9efe6fe2a051d6d4daf06e",
        }
        for filename, expected_digest in governed_sources.items():
            source = resource_root / filename
            self.assertTrue(source.is_file())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_digest)

        nda = records.filtered(lambda item: item.code == "S4-NDA")
        self.assertEqual(nda.master_file_id, "LOCAL-S4-NDA-REUSABLE-ODOO-MASTER-R1")
        self.assertEqual(
            nda.source_sha256,
            "cdccee7ebe36c160e44a03b38281ead11f180c02284affab9b1bfc2ea1e093a9",
        )
        self.assertEqual(nda.expected_page_count, 4)
        self.assertFalse(nda.approved_for_internal_uat_generation)
        self.assertFalse(nda.customer_issue_allowed)

    def test_customer_ready_commercial_masters_have_separate_template_qa(self):
        codes = ["LGC-03", "LGD-03", "LGV-03", "TLC-03", "TLL-03", "SB-03", "PG-03", "PB-SB-03"]
        records = self.env["hjig.sseries.document.template"].search([("code", "in", codes)])
        self.assertEqual(set(records.mapped("code")), set(codes))
        self.assertFalse(records.filtered(lambda item: item.rendering_status != "ready"))
        self.assertFalse(records.filtered(lambda item: not item.template_visual_qa_verified))
        self.assertFalse(records.filtered(lambda item: not item.template_content_qa_verified))
        self.assertFalse(records.filtered("customer_issue_allowed"))
