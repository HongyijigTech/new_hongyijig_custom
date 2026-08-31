import base64
from copy import deepcopy

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSSeriesWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Intake = cls.env["hjig.sseries.intake.submission"]
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def get_or_create_user(values):
            user = Users.with_context(active_test=False).search([
                "|",
                ("login", "=ilike", values["login"]),
                ("partner_id.email", "=ilike", values["email"]),
            ], limit=1)
            if user:
                requested_group_ids = values["group_ids"][0][2]
                user.write({
                    "active": True,
                    "company_ids": [(4, values["company_id"])],
                    "group_ids": [(4, group_id) for group_id in requested_group_ids],
                })
                return user
            return Users.create(values)

        cls.reviewer = get_or_create_user({
            "name": "S-Series UAT Reviewer",
            "login": "sseries-uat-reviewer@example.com",
            "email": "sseries-uat-reviewer@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref(
                "new_hongyijig_custom.group_hjig_sseries_user"
            ).id])],
        })
        cls.manager = get_or_create_user({
            "name": "S-Series UAT Manager",
            "login": "sseries-uat-manager@example.com",
            "email": "sseries-uat-manager@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref(
                "new_hongyijig_custom.group_hjig_sseries_manager"
            ).id])],
        })
        cls.document_preparer = get_or_create_user({
            "name": "S-Series UAT Document Preparer",
            "login": "sseries-uat-document-preparer@example.com",
            "email": "sseries-uat-document-preparer@example.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref(
                "new_hongyijig_custom.group_hjig_sseries_manager"
            ).id])],
        })
        cls.intake_owner = get_or_create_user({
            "name": "Intake Accountability",
            "login": "intake@thehongyijig.com",
            "email": "intake@thehongyijig.com",
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.business_crm_owner = get_or_create_user({
            "name": "Business CRM Accountability",
            "login": "businesscrm@thehongyijig.com",
            "email": "businesscrm@thehongyijig.com",
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

    def _sourcebridge_payload(self):
        payload = self._payload("SOURCEBRIDGE-0001")
        payload.update({
            "engagement_model": "SOURCEBRIDGE_ONLY",
            "services": {"overseas_sourcing_supplier_development": True},
            "sourcebridge_details": {
                "project_level": {
                    "sourcing_objective": "Qualify a controlled supply route for two components.",
                    "sourcing_package_count": 2,
                },
                "components": [
                    {
                        "component_name": "Control Housing",
                        "component_type": "Plastic Component",
                        "component_function": "Protect the control assembly",
                        "preferred_solution_route": "Supplier RFQ and validation",
                        "material_grade": "ABS",
                        "technical_specification_status": "Preliminary",
                        "expected_year_1_quantity": 1000,
                    },
                    {
                        "component_name": "Mounting Bracket",
                        "component_type": "Metal Component",
                        "component_function": "Mount the control assembly",
                        "preferred_solution_route": "Supplier RFQ and sample approval",
                        "material_grade": "SS304",
                        "technical_specification_status": "Released drawing",
                        "expected_year_1_quantity": 1000,
                    },
                ],
            },
        })
        return payload

    def _portfolio_payload(self):
        project = {
            "client_project_id": "PG-WORKFLOW-001",
            "project_name": "Portfolio Child One",
            "current_project_stage": "Concept",
            "expected_start_window": "Within 30 Days",
            "product_category": "Industrial",
            "duration_months": 8,
            "mould_count": 1,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "PROGRAMME_GOVERNANCE",
            "services": {"product_design": True},
        }
        second = deepcopy(project)
        second.update({
            "client_project_id": "PG-WORKFLOW-002",
            "project_name": "Portfolio Child Two",
        })
        return {
            "form_type": "PORTFOLIOGUARD",
            "client_submission_id": "PG-WORKFLOW-UMBRELLA-0001",
            "frontend_spec_version": "PortfolioGuard-v1.7",
            "submitted_at": "2026-08-30T05:00:00Z",
            "customer": {
                "company_name": "Portfolio Workflow Private Limited",
                "customer_contact_name": "Portfolio Workflow Contact",
                "customer_email": "portfolio-workflow@example.com",
            },
            "portfolio": {"projects_defined_count": 2},
            "projects": [project, second],
            "consent_given": True,
        }

    def _prepare_and_approve(self, artifact, label):
        artifact.with_user(self.reviewer).write({
            "document_data": self._pdf(label),
            "document_filename": "%s.pdf" % label,
        })
        artifact.with_user(self.manager).action_verify_visual_qa()
        artifact.with_user(self.manager).action_verify_content_qa()
        artifact.with_user(self.manager).action_approve()
        self.assertEqual(artifact.state, "approved")
        self.assertTrue(artifact.document_sha256)

    def _generate_and_approve(self, artifact):
        # Simulate a future versioned authority promotion for renderer lifecycle tests.
        # Production data keeps these candidates fail-closed until their own approval release.
        artifact.template_id.with_context(install_mode=True).write({
            "approved_for_internal_uat_generation": True,
        })
        artifact.with_user(self.document_preparer).action_generate_controlled_draft()
        self.assertEqual(artifact.state, "draft")
        self.assertEqual(
            artifact.rendered_page_count,
            artifact.render_manifest_json["expected_page_count"],
        )
        self.assertEqual(artifact.render_manifest_json["unresolved_placeholder_count"], 0)
        self.assertTrue(base64.b64decode(artifact.document_data).startswith(b"%PDF-"))
        artifact.with_user(self.manager).action_verify_visual_qa()
        artifact.with_user(self.manager).action_verify_content_qa()
        artifact.with_user(self.manager).action_approve()
        self.assertEqual(artifact.state, "approved")

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
            "customer_signature_received": True,
            "hongyi_countersigned": True,
            "acceptance_reference": "SIGNED-LGC-UAT-001",
            "acceptance_date": "2026-08-30",
        })
        case.with_user(self.manager).action_record_customer_acceptance()
        self.assertEqual(case.stage, "s4_activation")

        order_punch = case.artifact_ids.filtered(lambda item: item.code == "S5-ORDER-PUNCH")
        self._generate_and_approve(order_punch)
        case.with_user(self.manager).write({
            "proforma_reference": "PI-UAT-001",
            "finance_approved": True,
            "payment_received": True,
            "payment_evidence_reference": "BANK-UAT-001",
            "tax_invoice_reference": "TAX-UAT-001",
        })
        with self.assertRaisesRegex(ValidationError, "Proforma Invoice artifact"):
            case.with_user(self.manager).action_complete_activation()
        self._prepare_and_approve(
            case.artifact_ids.filtered(lambda item: item.code == "S5-PROFORMA"),
            "proforma-invoice",
        )
        case.with_user(self.manager).tax_invoice_reference = False
        with self.assertRaisesRegex(ValidationError, "Final/Tax Invoice reference"):
            case.with_user(self.manager).action_complete_activation()
        case.with_user(self.manager).tax_invoice_reference = "TAX-UAT-001"
        case.with_user(self.manager).action_complete_activation()
        self.assertEqual(case.stage, "s6_handover")
        self.assertTrue(case.order_number.startswith("HJIG-ORD-"))
        self.assertEqual(case.sale_order_id.state, "sale")

        team_handover = case.artifact_ids.filtered(lambda item: item.code == "S6-TEAM-HANDOVER")
        self._generate_and_approve(team_handover)
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
        b0_artifact = case.artifact_ids.filtered(
            lambda item: item.code == "B0-HANDOVER-MANIFEST"
        )
        self.assertEqual(len(b0_artifact), 1)
        self.assertEqual(b0_artifact.state, "required")
        with self.assertRaises(UserError):
            case.b0_manifest_id.write({"name": "Changed"})

    def test_one_crm_opportunity_routes_accountability_and_embeds_sseries(self):
        submission = self.Intake.ingest_payload(
            self._payload("CRM-SPINE-0001")
        )["submission"]
        case = submission.case_ids
        lead = case.lead_id
        self.assertTrue(lead)
        self.assertEqual(lead.stage_id, self.env.ref(
            "new_hongyijig_custom.crm_stage_hjig_pre_fd"
        ))
        self.assertEqual(lead.user_id, self.intake_owner)
        self.assertEqual(lead.hjig_accountability_phase, "pre_fd_fd")
        self.assertEqual(lead.hjig_accountable_email, "intake@thehongyijig.com")
        self.assertEqual(lead.hjig_sseries_case_ids, case)
        self.assertEqual(lead.hjig_sseries_case_count, 1)

        lead.write({"stage_id": self.env.ref(
            "new_hongyijig_custom.crm_stage_hjig_fd_series"
        ).id})
        self.assertEqual(lead.user_id, self.intake_owner)
        lead.write({"stage_id": self.env.ref(
            "new_hongyijig_custom.crm_stage_hjig_p_series"
        ).id})
        self.assertEqual(lead.user_id, self.business_crm_owner)

        case.with_user(self.manager).action_start_internal_review()
        self.assertEqual(lead.stage_id, self.env.ref(
            "new_hongyijig_custom.crm_stage_hjig_s_series"
        ))
        self.assertEqual(lead.user_id, self.business_crm_owner)
        self.assertEqual(lead.hjig_accountability_phase, "p_s")
        self.assertEqual(lead.hjig_accountable_email, "businesscrm@thehongyijig.com")

        action = lead.with_user(self.manager).action_open_hjig_sseries()
        self.assertEqual(action["res_id"], case.id)
        self.assertEqual(action["view_mode"], "form")

    def test_portfolioguard_children_share_one_crm_opportunity(self):
        submission = self.Intake.ingest_payload(self._portfolio_payload())["submission"]
        cases = submission.case_ids
        self.assertEqual(len(cases), 2)
        self.assertEqual(len(cases.mapped("lead_id")), 1)
        lead = cases.mapped("lead_id")
        self.assertEqual(lead.hjig_sseries_case_count, 2)
        self.assertEqual(lead.user_id, self.intake_owner)
        cases.with_user(self.manager).action_start_internal_review()
        self.assertEqual(lead.user_id, self.business_crm_owner)
        self.assertEqual(lead.stage_id, self.env.ref(
            "new_hongyijig_custom.crm_stage_hjig_s_series"
        ))

    def test_separate_sseries_menu_is_hidden_from_employee_navigation(self):
        menu = self.env.ref("new_hongyijig_custom.menu_hjig_sseries")
        self.assertEqual(menu.group_ids, self.env.ref("base.group_no_one"))

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
            artifact.with_user(self.manager).action_verify_visual_qa()

    def test_nda_checkbox_cannot_replace_execution_and_controlled_artifact_evidence(self):
        case = self.Intake.ingest_payload(self._payload("NDA-GATE-0001"))["submission"].case_ids
        case.action_start_internal_review()
        case.write({
            "reviewer_id": self.reviewer.id,
            "programme_route": "launchguard_complete",
            "scope_confirmed": True,
            "internal_review_summary": "NDA evidence-gate regression scope confirmed.",
        })
        case.with_user(self.manager).action_approve_internal_review()
        case.write({
            "governance_decision": "go",
            "risk_level": "medium",
            "governance_summary": "GO subject to executed NDA evidence.",
        })
        case.with_user(self.manager).action_approve_governance()
        case.with_user(self.manager).write({
            "approved_governance_fee": 350000,
            "payment_terms_summary": "60% on acceptance and 40% before final controlled release.",
        })
        case.with_user(self.manager).action_prepare_quotation()
        proposal = case.artifact_ids.filtered(lambda item: item.code == "LGC-03")
        self._prepare_and_approve(proposal, "nda-gate-proposal")
        proposal.with_user(self.manager).user_final_approval = True
        proposal.with_user(self.manager).action_allow_customer_issue()
        case.with_user(self.manager).write({
            "nda_required": True,
            "nda_completed": True,
            "acceptance_basis": "signed_proposal",
            "customer_signature_received": True,
            "hongyi_countersigned": True,
            "acceptance_reference": "SIGNED-NDA-GATE-UAT-001",
            "acceptance_date": "2026-08-31",
        })

        with self.assertRaisesRegex(ValidationError, "reference and effective date"):
            case.with_user(self.manager).action_record_customer_acceptance()

        case.with_user(self.manager).write({
            "nda_reference": "NDA-NDA-GATE-UAT-001",
            "nda_effective_date": "2026-08-31",
            "nda_customer_signed": True,
            "nda_hongyi_signed": True,
        })
        with self.assertRaisesRegex(ValidationError, "exact-master NDA artifact"):
            case.with_user(self.manager).action_record_customer_acceptance()
        nda_artifact = case.artifact_ids.filtered(lambda item: item.code == "S4-NDA")
        self.assertEqual(len(nda_artifact), 1)
        self.assertEqual(nda_artifact.state, "required")
        self.assertFalse(nda_artifact.customer_issue_allowed)

    def test_pending_nda_candidate_cannot_use_odoo_renderer(self):
        submission = self.Intake.ingest_payload(self._payload("WORKFLOW-AUTHORITY-0001"))["submission"]
        case = submission.case_ids
        template = self.env.ref("new_hongyijig_custom.sseries_template_s4_nda")
        self.assertFalse(template.approved_for_internal_uat_generation)
        self.assertEqual(
            template.authority_status,
            "REUSABLE_INTERNAL_UAT_USER_AND_LEGAL_APPROVAL_PENDING",
        )
        artifact = self.env["hjig.sseries.artifact"].with_context(
            hjig_sseries_workflow=True
        ).create({
            "name": "%s / S4-NDA" % case.name,
            "case_id": case.id,
            "template_id": template.id,
        })
        with self.assertRaisesRegex(ValidationError, "not approved for internal-UAT generation"):
            artifact.with_user(self.document_preparer).action_generate_controlled_draft()

    def test_sourcebridge_only_releases_standalone_engagement_and_components(self):
        case = self.Intake.ingest_payload(self._sourcebridge_payload())["submission"].case_ids
        case.action_start_internal_review()
        case.write({
            "reviewer_id": self.reviewer.id,
            "programme_route": "sourcebridge_only",
            "scope_confirmed": True,
            "internal_review_summary": "Standalone SourceBridge scope and component list confirmed.",
        })
        case.with_user(self.manager).action_approve_internal_review()
        case.write({
            "governance_decision": "go",
            "risk_level": "medium",
            "governance_summary": "GO for controlled sourcing and bilingual RFQ handover.",
        })
        case.with_user(self.manager).action_approve_governance()
        proposal = case.artifact_ids.filtered(lambda item: item.code == "SB-03")
        case.with_user(self.manager).write({
            "approved_governance_fee": 350000,
            "target_margin": 0.35,
            "payment_terms_summary": "60% on acceptance and 40% before final controlled release.",
        })
        case.with_user(self.manager).action_prepare_quotation()
        self._prepare_and_approve(proposal, "sourcebridge-proposal")
        proposal.with_user(self.manager).user_final_approval = True
        proposal.with_user(self.manager).action_allow_customer_issue()
        case.with_user(self.manager).write({
            "acceptance_basis": "signed_proposal",
            "customer_signature_received": True,
            "hongyi_countersigned": True,
            "acceptance_reference": "SIGNED-SBG-UAT-001",
            "acceptance_date": "2026-08-30",
        })
        case.with_user(self.manager).action_record_customer_acceptance()
        self._generate_and_approve(
            case.artifact_ids.filtered(lambda item: item.code == "S5-ORDER-PUNCH")
        )
        self._prepare_and_approve(
            case.artifact_ids.filtered(lambda item: item.code == "S5-PROFORMA"),
            "sourcebridge-proforma-invoice",
        )
        case.with_user(self.manager).write({
            "proforma_reference": "PI-SBG-UAT-001",
            "finance_approved": True,
            "payment_received": True,
            "payment_evidence_reference": "BANK-SBG-UAT-001",
            "tax_invoice_reference": "TAX-SBG-UAT-001",
        })
        case.with_user(self.manager).action_complete_activation()
        self.assertEqual(case.stage, "s5_sourcing")
        for code in ("S6-CHINA-HANDOVER", "S6-SUPPLIER-RFQ-EN", "S6-SUPPLIER-RFQ-ZH"):
            self._generate_and_approve(case.artifact_ids.filtered(lambda item, c=code: item.code == c))
        case.with_user(self.manager).action_complete_sourcing_pack()
        self._generate_and_approve(
            case.artifact_ids.filtered(lambda item: item.code == "S6-TEAM-HANDOVER")
        )
        case.with_user(self.manager).write({
            "handover_owner_id": self.reviewer.id,
            "handover_accepted": True,
        })
        case.with_user(self.manager).action_release_b0()

        engagement = case.sourcebridge_engagement_id
        self.assertEqual(case.stage, "b0_released")
        self.assertTrue(case.project_id.x_project_code.startswith("HJ-SBG-"))
        self.assertEqual(case.project_id.hjig_programme, "sourcebridge_only")
        self.assertTrue(engagement.standalone)
        self.assertFalse(case.programme_run_id)
        self.assertEqual(engagement.project_id, case.project_id)
        self.assertEqual(engagement.sale_order_id, case.sale_order_id)
        self.assertEqual(len(engagement.component_ids), 2)
        self.assertEqual(case.b0_manifest_id.sourcebridge_engagement_id, engagement)

    def test_portfolioguard_uses_one_umbrella_order_and_child_b0_runs(self):
        submission = self.Intake.ingest_payload(self._portfolio_payload())["submission"]
        cases = submission.case_ids.sorted("id")
        lead = cases[0]
        self.assertTrue(lead.portfolio_commercial_lead)
        self.assertFalse(cases[1].portfolio_commercial_lead)

        for child in cases:
            child.action_start_internal_review()
            child.write({
                "reviewer_id": self.reviewer.id,
                "programme_route": "launchguard_complete",
                "scope_confirmed": True,
                "internal_review_summary": "Portfolio child identity, scope and route confirmed.",
            })
            child.with_user(self.manager).action_approve_internal_review()
            child.write({
                "governance_decision": "go",
                "risk_level": "medium",
                "governance_summary": "GO under one PortfolioGuard umbrella commercial record.",
            })
            child.with_user(self.manager).action_approve_governance()

        proposals = cases.mapped("artifact_ids").filtered(lambda item: item.code == "PG-03")
        self.assertEqual(len(proposals), 1)
        cases[0].with_user(self.manager).write({
            "approved_governance_fee": 300000,
            "payment_terms_summary": "60% on acceptance and 40% before final controlled release.",
        })
        cases[1].with_user(self.manager).write({"approved_governance_fee": 200000})
        lead.with_user(self.manager).action_prepare_quotation()

        self.assertEqual(len(cases.mapped("sale_order_id")), 1)
        self.assertEqual(len(lead.sale_order_id.order_line), 2)
        self.assertEqual(lead.sale_order_id.amount_untaxed, 500000)
        self.assertEqual(len(set(cases.mapped("proposal_number"))), 1)
        with self.assertRaises(UserError):
            cases[1].with_user(self.manager).action_prepare_quotation()

        proposal = proposals
        self._prepare_and_approve(proposal, "portfolio-umbrella-proposal")
        proposal.with_user(self.manager).user_final_approval = True
        proposal.with_user(self.manager).action_allow_customer_issue()
        lead.with_user(self.manager).write({
            "acceptance_basis": "signed_proposal",
            "customer_signature_received": True,
            "acceptance_reference": "SIGNED-PG-UAT-001",
            "acceptance_date": "2026-08-30",
        })
        with self.assertRaises(ValidationError):
            lead.with_user(self.manager).action_record_customer_acceptance()
        lead.with_user(self.manager).hongyi_countersigned = True
        lead.with_user(self.manager).action_record_customer_acceptance()
        self.assertEqual(set(cases.mapped("stage")), {"s4_activation"})

        self._prepare_and_approve(
            lead.artifact_ids.filtered(lambda item: item.code == "S5-ORDER-PUNCH"),
            "portfolio-order-punch",
        )
        self._prepare_and_approve(
            lead.artifact_ids.filtered(lambda item: item.code == "S5-PROFORMA"),
            "portfolio-proforma-invoice",
        )
        lead.with_user(self.manager).write({
            "proforma_reference": "PI-PG-UAT-001",
            "finance_approved": True,
            "payment_received": True,
            "payment_evidence_reference": "BANK-PG-UAT-001",
            "tax_invoice_reference": "TAX-PG-UAT-001",
        })
        lead.with_user(self.manager).action_complete_activation()
        self.assertEqual(set(cases.mapped("stage")), {"s6_handover"})
        self.assertEqual(len(set(cases.mapped("order_number"))), 1)

        for child in cases:
            self._prepare_and_approve(
                child.artifact_ids.filtered(lambda item: item.code == "S6-TEAM-HANDOVER"),
                "portfolio-team-handover-%s" % child.id,
            )
            child.with_user(self.manager).write({
                "handover_owner_id": self.reviewer.id,
                "handover_accepted": True,
            })
            child.with_user(self.manager).action_release_b0()

        self.assertEqual(set(cases.mapped("stage")), {"b0_released"})
        self.assertEqual(len(cases.mapped("project_id")), 2)
        self.assertEqual(len(cases.mapped("programme_run_id")), 2)
        self.assertEqual(len(cases.mapped("b0_manifest_id")), 2)
        self.assertEqual(len(cases.mapped("portfolio_guard_id")), 1)
        self.assertEqual(cases.mapped("programme_run_id.portfolio_guard_id"), lead.portfolio_guard_id)
        self.assertEqual(len(set(cases.mapped("programme_run_id.sale_order_id"))), 1)

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
