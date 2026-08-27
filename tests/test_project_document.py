from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from psycopg2.errors import UniqueViolation


@tagged("post_install", "-at_install")
class TestProjectDocumentGovernance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Document Owner",
            "login": "document.owner@test.invalid",
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Document Approver",
            "login": "document.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_document_controller").id,
            ])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "LaunchGuard Controlled Project",
            "hjig_project_record_type": "customer",
            "x_project_code": "hj-lgc-2026-0001",
        })

    def _create_document(self, **overrides):
        values = {
            "project_id": self.project.id,
            "register_type": "programme_internal",
            "document_class": "project_working",
            "title": "Mould Plan",
            "document_type": "Engineering Plan",
            "revision": "R00",
            "owner_id": self.owner.id,
            "approver_id": self.approver.id,
            "drive_url": "https://drive.google.com/example",
        }
        values.update(overrides)
        return self.env["hjig.project.document"].create(values)

    def test_project_code_is_normalized_and_unique(self):
        self.assertEqual(self.project.x_project_code, "HJ-LGC-2026-0001")
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env["project.project"].create({
                "name": "Duplicate Code",
                "hjig_project_record_type": "customer",
                "x_project_code": "HJ-LGC-2026-0001",
            })

    def test_customer_project_requires_valid_code(self):
        with self.assertRaises(ValidationError):
            self.env["project.project"].create({
                "name": "Missing Code",
                "hjig_project_record_type": "customer",
            })
        with self.assertRaises(ValidationError):
            self.env["project.project"].create({
                "name": "Bad Code",
                "hjig_project_record_type": "customer",
                "x_project_code": "LGC-1",
            })

    def test_project_code_locks_after_first_document(self):
        self._create_document()
        with self.assertRaises(ValidationError):
            self.project.x_project_code = "HJ-LGC-2026-0002"

    def test_master_reference_cannot_enter_customer_register(self):
        with self.assertRaises(ValidationError):
            self._create_document(
                register_type="customer",
                document_class="master_reference",
            )

    def test_customer_controlled_cannot_enter_internal_register(self):
        with self.assertRaises(ValidationError):
            self._create_document(document_class="customer_controlled")

    def test_non_drive_link_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_document(drive_url="https://example.com/uncontrolled")

    def test_approval_freezes_document(self):
        document = self._create_document(effective_date="2026-08-27")
        document.action_submit_review()
        document.with_user(self.approver).action_approve()
        self.assertEqual(document.status, "approved")
        with self.assertRaises(ValidationError):
            document.title = "Changed after approval"
        with self.assertRaises(UserError):
            document.unlink()

    def test_new_revision_supersedes_approved_document_with_ecn(self):
        first = self._create_document(effective_date="2026-08-27")
        first.action_submit_review()
        first.with_user(self.approver).action_approve()

        second = self._create_document(
            revision="R01",
            status="review",
            effective_date="2026-08-28",
            supersedes_id=first.id,
            ecn_reference="ECN-2026-0001",
        )
        second.with_user(self.approver).action_approve()

        self.assertEqual(first.status, "superseded")
        self.assertEqual(first.superseded_by_id, second)
        self.assertEqual(second.status, "approved")
