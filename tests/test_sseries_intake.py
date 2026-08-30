from copy import deepcopy

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSSeriesIntake(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Intake = cls.env["hjig.sseries.intake.submission"]

    def _programme_builder_payload(self):
        return {
            "form_type": "PROGRAMME_BUILDER",
            "client_submission_id": "PB-ODOO-UAT-0001",
            "frontend_spec_version": "ProgrammeBuilder-V2",
            "submitted_at": "2026-08-30T05:00:00Z",
            "company_name": "UAT Customer Private Limited",
            "customer_contact_name": "UAT Contact",
            "customer_email": "uat@example.com",
            "customer_country": "India",
            "project_name": "UAT Programme Builder Project",
            "current_project_stage": "Concept",
            "customer_stated_product_category": "Industrial",
            "customer_stated_mould_count": 2,
            "customer_expected_duration_months": 8,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "PROGRAMME_GOVERNANCE",
            "services": {"product_design": True},
            "existing_hongyi_commercial": {"already_contracted": False, "contracted_scope_type": "No"},
            "consent_given": True,
        }

    def _portfolio_guard_payload(self):
        base_project = {
            "client_project_id": "PG-PROJECT-001",
            "project_name": "Portfolio Project One",
            "current_project_stage": "Supplier Selection",
            "expected_start_window": "Within 30 Days",
            "product_category": "Consumer Product",
            "duration_months": 9,
            "mould_count": 1,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "SOURCEBRIDGE_ONLY",
            "services": {"overseas_sourcing_supplier_development": True},
            "sourcebridge_details": {
                "project_level": {
                    "sourcing_objective": "Identify and validate a governed supply route",
                    "sourcing_package_count": 1,
                },
                "components": [{
                    "component_name": "Control Housing",
                    "component_type": "Plastic Component",
                    "component_function": "Protect the control assembly",
                    "preferred_solution_route": "Supplier RFQ and validation",
                    "expected_year_1_quantity": 1000,
                }],
            },
        }
        second = deepcopy(base_project)
        second.update({
            "client_project_id": "PG-PROJECT-002",
            "project_name": "Portfolio Project Two",
        })
        return {
            "form_type": "PORTFOLIOGUARD",
            "client_submission_id": "PG-ODOO-UAT-0001",
            "frontend_spec_version": "PortfolioGuard-v1.7",
            "customer": {
                "company_name": "Portfolio UAT Customer",
                "customer_contact_name": "Portfolio Contact",
                "customer_email": "portfolio@example.com",
            },
            "portfolio": {"projects_defined_count": 2},
            "projects": [base_project, second],
            "consent_given": True,
        }

    def test_programme_builder_creates_immutable_submission_project_and_case(self):
        result = self.Intake.ingest_payload(self._programme_builder_payload(), "100")
        submission = result["submission"]
        self.assertFalse(result["idempotent"])
        self.assertEqual(submission.project_count, 1)
        self.assertEqual(submission.case_count, 1)
        self.assertEqual(submission.case_ids.stage, "s0_received")
        with self.assertRaises(UserError):
            submission.write({"company_name": "Changed"})

    def test_same_payload_is_idempotent_and_conflicting_payload_is_blocked(self):
        payload = self._programme_builder_payload()
        first = self.Intake.ingest_payload(payload, "100")
        second = self.Intake.ingest_payload(deepcopy(payload), "101")
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["submission"], second["submission"])
        conflict = deepcopy(payload)
        conflict["project_name"] = "Conflicting Project"
        with self.assertRaises(ValidationError):
            self.Intake.ingest_payload(conflict, "102")

    def test_portfolio_guard_creates_exact_project_cases_and_components(self):
        submission = self.Intake.ingest_payload(self._portfolio_guard_payload())["submission"]
        self.assertEqual(submission.project_count, 2)
        self.assertEqual(submission.case_count, 2)
        self.assertEqual(len(submission.project_ids.mapped("component_ids")), 2)
        self.assertEqual(set(submission.project_ids.mapped("client_project_id")), {
            "PG-PROJECT-001", "PG-PROJECT-002",
        })

    def test_portfolio_guard_accepts_unknown_project_duration_for_internal_review(self):
        payload = self._portfolio_guard_payload()
        for project in payload["projects"]:
            project.pop("duration_months")
            project["customer_expected_duration_months"] = None
        submission = self.Intake.ingest_payload(payload)["submission"]
        self.assertEqual(set(submission.project_ids.mapped("expected_duration_months")), {0})
        self.assertEqual(set(submission.case_ids.mapped("stage")), {"s0_received"})

    def test_duplicate_portfolio_project_id_is_blocked(self):
        payload = self._portfolio_guard_payload()
        payload["projects"][1]["client_project_id"] = payload["projects"][0]["client_project_id"]
        with self.assertRaises(ValidationError):
            self.Intake.ingest_payload(payload)

    def test_public_payload_cannot_supply_odoo_ids(self):
        payload = self._programme_builder_payload()
        payload["odoo_partner_id"] = 7
        with self.assertRaises(ValidationError):
            self.Intake.ingest_payload(payload)

    def test_case_starts_internal_review_only_through_action(self):
        case = self.Intake.ingest_payload(self._programme_builder_payload())["submission"].case_ids
        with self.assertRaises(ValidationError):
            case.write({"stage": "s1_review"})
        case.action_start_internal_review()
        self.assertEqual(case.stage, "s1_review")
        self.assertEqual(case.reviewer_id, self.env.user)
