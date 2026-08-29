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
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
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
            "x_project_code": "hj-tst-2099-9001",
        })
        cls.owner_designation = cls.env["hjig.governance.designation"].create({
            "code": "TEST-OWNER",
            "name": "Test Owner Designation",
            "category": "project",
            "holder_ids": [(6, 0, [cls.owner.id])],
        })
        cls.approver_designation = cls.env["hjig.governance.designation"].create({
            "code": "TEST-APPROVER",
            "name": "Test Approver Designation",
            "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.env["hjig.project.designation.assignment"].create([{
            "project_id": cls.project.id,
            "designation_id": cls.owner_designation.id,
            "holder_ids": [(6, 0, [cls.owner.id])],
        }, {
            "project_id": cls.project.id,
            "designation_id": cls.approver_designation.id,
            "holder_ids": [(6, 0, [cls.approver.id])],
        }])
        cls.stage = cls.env["hjig.launchguard.stage"].create({
            "code": "TEST-GATE",
            "name": "Test Gate",
            "sequence": 1,
            "stage_type": "technical_gate",
        })
        cls.other_stage = cls.env["hjig.launchguard.stage"].create({
            "code": "OTHER-GATE",
            "name": "Other Gate",
            "sequence": 2,
            "stage_type": "technical_gate",
        })
        cls.artifact = cls.env["hjig.governance.artifact.master"].create({
            "code": "TEST-FORM",
            "name": "Mould Plan",
            "artifact_type": "form",
            "applicable_stage_ids": [(6, 0, [cls.stage.id])],
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "default_register_type": "programme_internal",
            "default_document_class": "project_working",
            "revision": "1.0",
        })

    def _create_document(self, **overrides):
        values = {
            "project_id": self.project.id,
            "artifact_master_id": self.artifact.id,
            "stage_id": self.stage.id,
            "revision": "R00",
            "drive_url": "https://drive.google.com/example",
        }
        values.update(overrides)
        return self.env["hjig.project.document"].create(values)

    def test_project_code_is_normalized_and_unique(self):
        self.assertEqual(self.project.x_project_code, "HJ-TST-2099-9001")
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env["project.project"].create({
                "name": "Duplicate Code",
                "hjig_project_record_type": "customer",
                "x_project_code": "HJ-TST-2099-9001",
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
        document.with_user(self.owner).action_submit_review()
        document.with_user(self.approver).action_approve()
        self.assertEqual(document.status, "approved")
        with self.assertRaises(ValidationError):
            document.title = "Changed after approval"
        with self.assertRaises(UserError):
            document.unlink()

    def test_new_revision_supersedes_approved_document_with_ecn(self):
        first = self._create_document(effective_date="2026-08-27")
        first.with_user(self.owner).action_submit_review()
        first.with_user(self.approver).action_approve()

        second = self._create_document(
            revision="R01",
            effective_date="2026-08-28",
            supersedes_id=first.id,
            ecn_reference="ECN-2026-0001",
        )
        second.with_user(self.owner).action_submit_review()
        second.with_user(self.approver).action_approve()

        self.assertEqual(first.status, "superseded")
        self.assertEqual(first.superseded_by_id, second)
        self.assertEqual(second.status, "approved")

    def test_stage_must_match_master(self):
        with self.assertRaises(ValidationError):
            self._create_document(stage_id=self.other_stage.id)

    def test_only_designation_holder_can_submit(self):
        document = self._create_document()
        with self.assertRaises(UserError):
            document.action_submit_review()

    def test_status_cannot_bypass_workflow(self):
        document = self._create_document()
        with self.assertRaises(ValidationError):
            document.status = "review"

    def test_used_master_is_immutable(self):
        self._create_document()
        with self.assertRaises(ValidationError):
            self.artifact.name = "Rewritten Master"

    def test_operating_catalogue_contains_all_sops_and_required_forms(self):
        master = self.env["hjig.governance.artifact.master"]
        sop_codes = set(master.search([("artifact_type", "=", "sop")]).mapped("code"))
        form_by_name = {
            record.name: record for record in master.search([("artifact_type", "=", "form")])
        }
        self.assertTrue({"SOP-%03d" % number for number in range(1, 14)}.issubset(sop_codes))
        self.assertGreaterEqual(len(form_by_name), 42)
        required_forms = {
            "Project Master", "SOR Creation Record", "BOP Lock Record", "Mould Planning Sheet",
            "Risk Register", "Issue Register", "ECN Register", "Part Visual Inspection Report",
            "Assembly Inspection Report", "Dimensional Inspection Report", "Project Execution Sheet",
            "Tool Manufacturing Progress Record", "Installation Checklist", "Site Trial Report",
            "Final Customer Acceptance", "Lessons Learned Register",
        }
        self.assertFalse(required_forms - set(form_by_name))

    def test_bop_uses_controlled_document_and_baseline_without_duplicate_model(self):
        bop_master = self.env.ref("new_hongyijig_custom.artifact_frm_004")
        bop_document = self.env["hjig.project.document"].create({
            "project_id": self.project.id,
            "artifact_master_id": bop_master.id,
            "stage_id": self.env.ref("new_hongyijig_custom.stage_tg01").id,
            "revision": "BOP-R00",
            "drive_url": "https://docs.google.com/spreadsheets/d/controlled-bop-record",
        })
        bop_baseline = self.env["hjig.baseline"].create({
            "project_id": self.project.id,
            "target_ref": "hjig.project.document,%s" % bop_document.id,
            "baseline_type": "bop",
            "revision": "BOP-R00",
            "effective_date": "2026-08-29",
            "approval_authority_designation_id": self.approver_designation.id,
        })
        self.assertEqual(bop_document.artifact_master_id.code, "FRM-004")
        self.assertEqual(bop_baseline.target_ref, bop_document)
        self.assertEqual(bop_baseline.baseline_type, "bop")
