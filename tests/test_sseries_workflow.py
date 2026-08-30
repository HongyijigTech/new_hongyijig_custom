import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSSeriesWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Intake = cls.env["hjig.sseries.intake.submission"]
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.reviewer = Users.create({
            "name": "S-Series UAT Reviewer",
            "login": "sseries-uat-reviewer@example.com",
            "email": "sseries-uat-reviewer@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref(
                "new_hongyijig_custom.group_hjig_sseries_user"
            ).id])],
        })
        cls.manager = Users.create({
            "name": "S-Series UAT Manager",
            "login": "sseries-uat-manager@example.com",
            "email": "sseries-uat-manager@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref(
                "new_hongyijig_custom.group_hjig_sseries_manager"
            ).id])],
        })
        template = cls.env.ref("new_hongyijig_custom.programme_launchguard_complete")
        cls.lgc_version = cls.env["hjig.programme.template.version"].search([
            ("template_id", "=", template.id),
            ("state", "=", "approved"),
            ("is_current", "=", True),
        ], limit=1)
        if not cls.lgc_version:
            cls.lgc_version = cls.env["hjig.programme.template.version"].with_context(
                hjig_programme_lifecycle=True
            ).create({
                "template_id": template.id,
                "version": "S-UAT-1.0",
                "state": "approved",
                "is_current": True,
                "effective_from": "2026-08-30",
            })

    def _payload(self, suffix="WORKFLOW-0001"):
        return {
            "form_type": "PROGRAMME_BUILDER",
            "client_submission_id": "PB-%s" % suffix,
            "frontend_spec_version": "ProgrammeBuilder-V2",
            "submitted_at": "2026-08-30T05:00:00Z",
            "company_name": "Workflow UAT Private Limited",
            "customer_contact_name": "Workflow Contact",
            "customer_email": "workflow-%s@example.com" % suffix.lower(),
            "customer_country": "India",
            "project_name": "Workflow UAT Project",
            "current_project_stage": "Concept",
            "customer_stated_product_category": "Industrial",
            "customer_stated_mould_count": 2,
            "customer_expected_duration_months": 8,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "PROGRAMME_GOVERNANCE",
            "services": {"product_design": True},
            "existing_hongyi_commercial": {"already_contracted": False},
            "consent_given": True,
        }

    def _pdf(self, label):
        return base64.b64encode(b"%PDF-1.4\n% " + label.encode() + b"\n%%EOF\n")

    def _prepare_and_approve(self, artifact, label):
        artifact.with_user(self.reviewer).write({
            "document_data": self._pdf(label),
            "document_filename": "%s.pdf" % label,
        })
        artifact.with_user(self.manager).action_verify_qa()
        artifact.with_user(self.manager).action_approve()
        self.assertEqual(artifact.state, "approved")
        self.assertTrue(artifact.document_sha256)

    def test_one_cockpit_progresses_to_immutable_b0_manifest(self):
        submission = self.Intake.ingest_payload(self._payload())["submission"]
        case = submission.case_ids
        self.assertEqual(submission.acknowledgement_state, "pending")

        case.action_start_internal_review()
        self.assertTrue(case.partner_id)
        self.assertTrue(case.lead_id)
        case.write({
            "reviewer_id": self.reviewer.id,
            "programme_route": "launchguard_complete",
            "scope_confirmed": True,
            "internal_review_summary": "Customer identity, scope and LaunchGuard route confirmed.",
        })
        case.with_user(self.manager).action_approve_internal_review()
        self.assertEqual(case.stage, "s2_assessment")

        case.write({
            "governance_decision": "go",
            "risk_level": "medium",
            "governance_summary": "GO with controlled commercial and execution boundaries.",
        })
        case.with_user(self.manager).action_approve_governance()
        self.assertEqual(case.stage, "s3_proposal")
        proposal = case.artifact_ids.filtered(lambda item: item.code == "LGC-03")
        self.assertEqual(len(proposal), 1)

        case.with_user(self.manager).write({
            "approved_governance_fee": 350000,
            "target_margin": 0.35,
            "payment_terms_summary": "60% on acceptance and 40% before final controlled release.",
        })
        case.with_user(self.manager).action_prepare_quotation()
        self.assertTrue(case.proposal_number.startswith("HJIG-LGC-"))
        self.assertEqual(case.sale_order_id.amount_untaxed, 350000)
        self.assertEqual(case.pricing_snapshot_json["approved_governance_fee"], 350000)

        self._prepare_and_approve(proposal, "lgc-proposal")
        proposal.with_user(self.manager).user_final_approval = True
        proposal.with_user(self.manager).action_allow_customer_issue()
        case.with_user(self.manager).write({
            "acceptance_basis": "signed_proposal",
            "acceptance_reference": "SIGNED-LGC-UAT-001",
            "acceptance_date": "2026-08-30",
        })
        case.with_user(self.manager).action_record_customer_acceptance()
        self.assertEqual(case.stage, "s4_activation")

        order_punch = case.artifact_ids.filtered(lambda item: item.code == "S5-ORDER-PUNCH")
        self._prepare_and_approve(order_punch, "order-punch")
        case.with_user(self.manager).write({
            "proforma_reference": "PI-UAT-001",
            "finance_approved": True,
            "payment_received": True,
            "payment_evidence_reference": "BANK-UAT-001",
            "tax_invoice_reference": "TAX-UAT-001",
        })
        case.with_user(self.manager).action_complete_activation()
        self.assertEqual(case.stage, "s6_handover")
        self.assertTrue(case.order_number.startswith("HJIG-ORD-"))
        self.assertEqual(case.sale_order_id.state, "sale")

        team_handover = case.artifact_ids.filtered(lambda item: item.code == "S6-TEAM-HANDOVER")
        self._prepare_and_approve(team_handover, "team-handover")
        case.with_user(self.manager).write({
            "handover_owner_id": self.reviewer.id,
            "handover_accepted": True,
        })
        case.with_user(self.manager).action_release_b0()
        self.assertEqual(case.stage, "b0_released")
        self.assertTrue(case.project_id.x_project_code.startswith("HJ-LGC-"))
        self.assertEqual(case.programme_run_id.sale_order_id, case.sale_order_id)
        self.assertEqual(case.b0_manifest_id.project_id, case.project_id)
        self.assertEqual(case.b0_manifest_id.programme_run_id, case.programme_run_id)
        self.assertTrue(case.b0_manifest_id.snapshot_sha256)
        with self.assertRaises(UserError):
            case.b0_manifest_id.write({"name": "Changed"})

    def test_unresolved_exact_master_fails_closed(self):
        submission = self.Intake.ingest_payload(self._payload("WORKFLOW-0002"))["submission"]
        case = submission.case_ids
        template = self.env.ref("new_hongyijig_custom.sseries_template_s4_nda")
        artifact = self.env["hjig.sseries.artifact"].with_context(
            hjig_sseries_workflow=True
        ).create({
            "name": "%s / S4-NDA" % case.name,
            "case_id": case.id,
            "template_id": template.id,
        })
        artifact.with_user(self.reviewer).write({
            "document_data": self._pdf("nda"),
            "document_filename": "nda.pdf",
        })
        with self.assertRaises(ValidationError):
            artifact.with_user(self.manager).action_verify_qa()

    def test_external_issue_cannot_skip_independent_gates(self):
        submission = self.Intake.ingest_payload(self._payload("WORKFLOW-0003"))["submission"]
        case = submission.case_ids
        template = self.env.ref("new_hongyijig_custom.sseries_template_lgc03")
        artifact = self.env["hjig.sseries.artifact"].with_context(
            hjig_sseries_workflow=True
        ).create({
            "name": "%s / LGC-03" % case.name,
            "case_id": case.id,
            "template_id": template.id,
        })
        with self.assertRaises(ValidationError):
            artifact.with_user(self.manager).action_allow_customer_issue()
        self._prepare_and_approve(artifact, "gated-proposal")
        with self.assertRaises(ValidationError):
            artifact.with_user(self.manager).action_allow_customer_issue()
