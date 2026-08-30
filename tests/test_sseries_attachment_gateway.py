import base64
from copy import deepcopy

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSSeriesAttachmentGateway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Gateway = cls.env["hjig.sseries.intake.attachment.gateway"]
        cls.Intake = cls.env["hjig.sseries.intake.submission"]

    def _upload_values(self, submission_id="PB-ATTACHMENT-UAT-0001", content=b"safe-image"):
        return {
            "client_submission_id": submission_id,
            "client_project_id": "",
            "component_index": 1,
            "attachment_type": "REFERENCE_IMAGE",
            "file_name": "reference-image.png",
            "mime_type": "image/png",
            "file_base64": base64.b64encode(content).decode(),
        }

    def _payload(self, gateway):
        return {
            "form_type": "PROGRAMME_BUILDER",
            "client_submission_id": gateway.client_submission_id,
            "frontend_spec_version": "ProgrammeBuilder-V2",
            "company_name": "Attachment UAT Customer",
            "customer_contact_name": "Attachment Contact",
            "customer_email": "attachment@example.invalid",
            "project_name": "Private Attachment Intake",
            "current_project_stage": "Concept",
            "customer_stated_product_category": "Industrial",
            "customer_stated_mould_count": 0,
            "customer_expected_duration_months": 6,
            "tooling_value_status": "Not Known Yet",
            "engagement_model": "SOURCEBRIDGE_ONLY",
            "services": {"overseas_sourcing_supplier_development": True},
            "sourcebridge_selected": True,
            "sourcebridge_details": {
                "project_level": {
                    "sourcing_objective": "Find a controlled component source",
                    "sourcing_package_count": 1,
                },
                "components": [{
                    "component_name": "Housing",
                    "component_function": "Protect the assembly",
                    "preferred_solution_route": "Supplier RFQ",
                    "expected_year_1_quantity": 1000,
                    "reference_image_attached": True,
                    "reference_image_file_id": gateway.name,
                    "reference_image_file_name": gateway.file_name,
                    "reference_image_mime_type": gateway.mime_type,
                    "reference_image_upload_status": "STORED_PRIVATE_UAT",
                }],
            },
            "consent_given": True,
        }

    def test_private_upload_is_idempotent_and_does_not_persist_transport_base64(self):
        first = self.Gateway.create(self._upload_values())
        second = self.Gateway.create(self._upload_values())
        self.assertEqual(first, second)
        self.assertFalse(first.file_base64)
        self.assertEqual(first.file_size_bytes, len(b"safe-image"))
        self.assertEqual(first.upload_status, "stored_private_uat")
        self.assertTrue(first.attachment_id)
        self.assertFalse(first.attachment_id.access_token)
        self.assertNotIn("access_token", first.file_url)

    def test_api_group_user_can_create_but_cannot_mutate_private_upload(self):
        api_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "S-Series Attachment API UAT",
            "login": "sseries-attachment-api-uat@example.invalid",
            "email": "sseries-attachment-api-uat@example.invalid",
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("new_hongyijig_custom.group_hjig_sseries_user").id,
            ])],
        })
        gateway = self.Gateway.with_user(api_user).create(
            self._upload_values(submission_id="PB-ATTACHMENT-API-UAT-0001")
        )
        self.assertTrue(gateway.attachment_id)
        with self.assertRaises(UserError):
            gateway.with_user(api_user).write({"file_name": "changed.png"})

    def test_final_intake_claims_file_for_exact_component(self):
        gateway = self.Gateway.create(self._upload_values())
        submission = self.Intake.ingest_payload(self._payload(gateway))["submission"]
        component = submission.project_ids.component_ids
        self.assertEqual(component.reference_image_attachment_id, gateway.attachment_id)
        self.assertEqual(gateway.submission_id, submission)
        self.assertEqual(gateway.project_id, component.project_id)
        self.assertEqual(gateway.component_id, component)
        self.assertEqual(gateway.attachment_id.res_model, component._name)
        self.assertEqual(gateway.attachment_id.res_id, component.id)

    def test_attachment_from_another_submission_is_rejected(self):
        gateway = self.Gateway.create(self._upload_values())
        payload = self._payload(gateway)
        payload["client_submission_id"] = "PB-ATTACHMENT-UAT-OTHER"
        with self.assertRaises(ValidationError):
            self.Intake.ingest_payload(payload)

    def test_dangerous_extension_and_invalid_base64_are_rejected(self):
        dangerous = self._upload_values()
        dangerous.update({
            "attachment_type": "TECHNICAL_FILE",
            "file_name": "payload.exe",
            "mime_type": "application/octet-stream",
        })
        with self.assertRaises(ValidationError):
            self.Gateway.create(dangerous)
        invalid = deepcopy(self._upload_values())
        invalid["file_base64"] = "%%%not-base64%%%"
        with self.assertRaises(ValidationError):
            self.Gateway.create(invalid)

    def test_upload_and_claim_records_are_immutable(self):
        gateway = self.Gateway.create(self._upload_values())
        with self.assertRaises(UserError):
            gateway.write({"file_name": "changed.png"})
        with self.assertRaises(UserError):
            gateway.unlink()
