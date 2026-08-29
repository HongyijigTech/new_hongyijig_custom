from odoo.tests import TransactionCase, tagged

from ..models.programme_architecture_authority import WEEKLY_CODES


@tagged("post_install", "-at_install")
class TestProgrammeArchitectureAuthority(TransactionCase):

    def test_lgc_mould_planning_and_weekly_reports_match_constitution(self):
        version = self.env["hjig.programme.template.version"].create({
            "template_id": self.env.ref(
                "new_hongyijig_custom.programme_launchguard_complete"
            ).id,
            "version": "ARCHITECTURE-TEST",
        })
        pa00 = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id,
            "stage_id": self.env.ref("new_hongyijig_custom.stage_pa00").id,
            "sequence": 10,
        })
        tg02 = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id,
            "stage_id": self.env.ref("new_hongyijig_custom.stage_tg02").id,
            "sequence": 20,
        })
        tg03 = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id,
            "stage_id": self.env.ref("new_hongyijig_custom.stage_tg03").id,
            "sequence": 30,
        })
        owner = self.env.ref("new_hongyijig_custom.designation_tool_design")
        approver = self.env.ref("new_hongyijig_custom.designation_project_manager")
        self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "ARCH-A005",
            "name": "A-005: Risk Register",
            "sequence": 40,
            "gate_line_id": pa00.id,
            "owner_designation_id": owner.id,
            "approver_designation_id": approver.id,
            "legacy_master_codes": "A-005",
        })
        a004 = self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "ARCH-A004",
            "name": "A-004: Tentative Mould Planning",
            "sequence": 50,
            "gate_line_id": tg02.id,
            "owner_designation_id": owner.id,
            "approver_designation_id": approver.id,
            "legacy_master_codes": "A-004",
        })
        self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "ARCH-WEEKLY",
            "name": "A-026 to A-031: Manufacturing Updates Report - Week 1 to Week 6",
            "sequence": 60,
            "gate_line_id": tg03.id,
            "owner_designation_id": owner.id,
            "approver_designation_id": approver.id,
            "legacy_source_task_id": 70001,
            "legacy_master_codes": "A-026,A-031",
            "execution_basis": "mould",
        })

        version._sync_founder_approved_architecture()

        self.assertEqual(a004.gate_line_id, pa00)
        weekly = version.activity_line_ids.filtered(
            lambda activity: (activity.legacy_master_codes or "") in WEEKLY_CODES
        )
        self.assertEqual(set(weekly.mapped("legacy_master_codes")), set(WEEKLY_CODES))
        self.assertEqual(len(weekly), 6)
        self.assertEqual(set(weekly.mapped("execution_basis")), {"mould"})
        self.assertEqual(len(weekly.filtered("legacy_source_task_id")), 1)

        # The operation is safe to repeat.
        version._sync_founder_approved_architecture()
        self.assertEqual(
            len(version.activity_line_ids.filtered(
                lambda activity: (activity.legacy_master_codes or "") in WEEKLY_CODES
            )),
            6,
        )
