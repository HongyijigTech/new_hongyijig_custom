from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.programme_activity_authority import SOURCE_REFERENCE, SOURCE_VERSION


@tagged("post_install", "-at_install")
class TestProgrammeActivityAuthority(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.version = cls.env["hjig.programme.template.version"].create({
            "template_id": cls.env.ref("new_hongyijig_custom.programme_launchguard_complete").id,
            "version": "AUTHORITY-TEST",
        })
        cls.gate = cls.env["hjig.programme.template.gate"].create({
            "version_id": cls.version.id,
            "stage_id": cls.env.ref("new_hongyijig_custom.stage_tg03").id,
            "sequence": 10,
        })
        cls.placeholder_owner = cls.env.ref("new_hongyijig_custom.designation_project_manager")
        cls.placeholder_approver = cls.env.ref("new_hongyijig_custom.designation_pmo_document_controller")

    def _activity(self, master_code, sequence):
        return self.env["hjig.programme.template.activity"].create({
            "version_id": self.version.id,
            "code": "AUTH-%s" % master_code.replace("-", ""),
            "name": "%s: authority audit" % master_code,
            "sequence": sequence,
            "gate_line_id": self.gate.id,
            "owner_designation_id": self.placeholder_owner.id,
            "approver_designation_id": self.placeholder_approver.id,
            "legacy_source_task_id": 50000 + sequence,
            "legacy_master_codes": master_code,
        })

    def test_locked_constitution_owner_and_support_mapping(self):
        expectations = {
            "A-024": ("SR-TOOL-DESIGN", set()),
            "A-042": ("PROJECT-COORD", set()),
            "CM-01": ("COMMERCIAL-LOGISTICS", {"ACCOUNTING-PAYMENTS"}),
            "CM-05": ("COMMERCIAL-LOGISTICS", {"ACCOUNTING-PAYMENTS"}),
            "A-026": ("SR-DEVELOPMENT-CHINA", set()),
            "A-017": ("VENDOR-SOURCING", {"PROJECT-COORD"}),
            "B8-01": ("SR-TOOL-DEVELOPMENT", set()),
        }
        activities = {
            code: self._activity(code, sequence * 10)
            for sequence, code in enumerate(expectations, start=1)
        }

        self.version._sync_founder_approved_activity_authority()

        for code, (owner, support) in expectations.items():
            activity = activities[code]
            self.assertEqual(activity.owner_designation_id.code, owner)
            self.assertEqual(activity.coordinator_designation_id.code, "PROJECT-COORD")
            self.assertEqual(set(activity.support_designation_ids.mapped("code")), support)
            self.assertEqual(activity.authority_source_reference, SOURCE_REFERENCE)
            self.assertEqual(activity.authority_source_version, SOURCE_VERSION)

    def test_unmarked_conflicting_combined_master_codes_are_rejected(self):
        activity = self._activity("A-024", 90)
        activity.legacy_master_codes = "A-024,A-042"
        with self.assertRaises(ValidationError):
            self.version._sync_founder_approved_activity_authority()

    def test_risk_register_activity_separates_owner_and_approver(self):
        activity = self._activity("A-005", 95)

        self.version._sync_founder_approved_activity_authority()

        self.assertEqual(activity.owner_designation_id.code, "PROJECT-MANAGER")
        self.assertEqual(activity.approver_designation_id.code, "PMO-DOC")

    def test_explicit_replacement_keeps_owner_and_records_both_support_roles(self):
        activity = self._activity("A-089", 100)
        activity.name = "Dispatch Confirmation Sign-Off (REPLACES A-089 + A-090)"
        activity.legacy_master_codes = "A-089,A-090"

        self.version._sync_founder_approved_activity_authority()

        self.assertEqual(activity.owner_designation_id, self.placeholder_owner)
        self.assertEqual(
            set(activity.support_designation_ids.mapped("code")),
            {"SR-TOOL-DESIGN", "SR-TOOL-DEVELOPMENT"},
        )
