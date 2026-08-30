import json
from copy import deepcopy

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSSeriesGateway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Gateway = cls.env["hjig.sseries.intake.gateway"]

    def _payload(self):
        return {
            "form_type": "PROGRAMME_BUILDER",
            "client_submission_id": "PB-N8N-GATEWAY-UAT-0001",
            "frontend_spec_version": "ProgrammeBuilder-V2",
            "company_name": "Gateway UAT Customer",
            "customer_contact_name": "Gateway Contact",
            "customer_email": "gateway@example.invalid",
            "project_name": "Gateway UAT Project",
            "current_project_stage": "Concept",
            "customer_stated_product_category": "Industrial",
            "customer_stated_mould_count": 1,
            "customer_expected_duration_months": 8,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "PROGRAMME_GOVERNANCE",
            "services": {"product_design": True},
            "existing_hongyi_commercial": {"already_contracted": False},
            "consent_given": True,
            "odoo_partner_id": "",
            "nested": {"odoo_opportunity_or_project_id": None},
        }

    def test_empty_legacy_odoo_fields_are_removed_before_governed_ingest(self):
        record = self.Gateway.create({"payload_json": json.dumps(self._payload())})
        self.assertEqual(record.client_submission_id, "PB-N8N-GATEWAY-UAT-0001")
        self.assertEqual(record.project_count, 1)
        self.assertFalse(record.idempotent)
        self.assertFalse(record.payload_json)
        self.assertNotIn("odoo_partner_id", record.submission_id.raw_payload_json)
        self.assertNotIn("odoo_opportunity_or_project_id", record.submission_id.raw_payload_json["nested"])

    def test_nonempty_public_odoo_identifier_is_blocked(self):
        payload = self._payload()
        payload["odoo_partner_id"] = 7
        with self.assertRaises(ValidationError):
            self.Gateway.create({"payload_json": json.dumps(payload)})

    def test_gateway_preserves_intake_idempotency_and_is_immutable(self):
        payload = self._payload()
        first = self.Gateway.create({"payload_json": json.dumps(payload)})
        second = self.Gateway.create({"payload_json": json.dumps(deepcopy(payload))})
        self.assertFalse(first.idempotent)
        self.assertTrue(second.idempotent)
        self.assertEqual(first.submission_id, second.submission_id)
        with self.assertRaises(UserError):
            second.write({"name": "Changed"})
        with self.assertRaises(UserError):
            second.unlink()
