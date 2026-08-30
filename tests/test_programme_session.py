from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProgrammeAdvisorySessions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner_user = cls.env["res.users"].create({
            "name": "Advisory Owner",
            "login": "advisory.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver_user = cls.env["res.users"].create({
            "name": "Advisory Approver",
            "login": "advisory.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_document_controller").id,
            ])],
        })
        cls.owner = cls.env["hjig.governance.designation"].create({
            "code": "ADVISORY-OWNER-TEST", "name": "Advisory Owner Test",
            "category": "project", "holder_ids": [(6, 0, [cls.owner_user.id])],
        })
        cls.approver = cls.env["hjig.governance.designation"].create({
            "code": "ADVISORY-APPROVER-TEST", "name": "Advisory Approver Test",
            "category": "governance", "holder_ids": [(6, 0, [cls.approver_user.id])],
        })
        cls.stage = cls.env["hjig.launchguard.stage"].create({
            "code": "TLL-TEST-STAGE", "name": "Advisory Test Stage",
            "sequence": 900, "stage_type": "advisory_session",
        })
        cls.artifact = cls.env["hjig.governance.artifact.master"].create({
            "code": "TLL-FRM-TEST", "name": "Blank Advisory Framework",
            "artifact_type": "form", "applicable_stage_ids": [(6, 0, [cls.stage.id])],
            "owner_designation_id": cls.owner.id,
            "approver_designation_id": cls.approver.id,
            "default_register_type": "programme_internal",
            "default_document_class": "project_working", "revision": "1.0",
        })
        cls.template = cls.env.ref("new_hongyijig_custom.programme_toollock_lite")
        cls.template.write({
            "execution_mode": "advisory_sessions",
            "owner_designation_id": cls.owner.id,
            "approver_designation_id": cls.approver.id,
        })
        cls.version = cls.env["hjig.programme.template.version"].create({
            "template_id": cls.template.id, "version": "TEST-1.0",
            "effective_from": "2026-08-28",
            "legacy_source_database": "legacy_test_db",
            "legacy_source_project_id": 5, "legacy_source_task_count": 12,
            "dependency_review_status": "verified", "evidence_review_status": "verified",
            "timing_review_status": "verified",
        })
        for number in range(1, 7):
            code = "TLL-S%02d" % number
            stage = cls.env["hjig.launchguard.stage"].search([("code", "=", code)], limit=1)
            framework = cls.env["hjig.governance.artifact.master"].search([
                ("code", "=", "FRM-TLL-%03d" % number)
            ], limit=1)
            cls.env["hjig.programme.template.session"].create({
                "version_id": cls.version.id, "code": code,
                "sequence": number * 10, "name": "Advisory Session %s" % number,
                "stage_id": stage.id,
                "indicative_duration": "Half day", "owner_designation_id": cls.owner.id,
                "approver_designation_id": cls.approver.id,
                "framework_artifact_id": framework.id,
                "legacy_source_task_ids": "%s,%s" % (number * 2 - 1, number * 2),
                "source_task_count": 2, "source_reference": "B-Series Constitution",
                "source_version": "v6.9",
            })
        cls.version.action_submit_review()
        cls.version.with_user(cls.approver_user).action_approve()
        cls.partner = cls.env["res.partner"].create({"name": "Advisory Customer"})

    def test_session_definition_reconciles_legacy_source(self):
        self.assertEqual(self.version.execution_mode, "advisory_sessions")
        self.assertEqual(len(self.version.session_line_ids), 6)
        self.assertEqual(sum(self.version.session_line_ids.mapped("source_task_count")), 12)
        self.assertEqual(self.version._definition_payload()["execution_mode"], "advisory_sessions")

    def test_session_programme_generates_sessions_not_gates_or_tasks(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id, "state": "sale"})
        project = self.env["project.project"].create({
            "name": "Advisory Project", "x_project_code": "HJ-TLL-2026-0001",
            "hjig_project_record_type": "customer",
            "hjig_authorized_user_ids": [(6, 0, [self.owner_user.id, self.approver_user.id])],
        })
        for designation, holder in ((self.owner, self.owner_user), (self.approver, self.approver_user)):
            self.env["hjig.project.designation.assignment"].create({
                "project_id": project.id,
                "designation_id": designation.id,
                "holder_ids": [(6, 0, [holder.id])],
            })
        run = self.env["hjig.programme.run"].create({
            "name": "HJ-TLL-2026-0001 — ToolLock Lite", "sale_order_id": order.id,
            "project_id": project.id, "template_version_id": self.version.id,
        })
        run.action_generate_execution()
        self.assertEqual(run.state, "generated")
        self.assertEqual(len(run.session_ids), 6)
        self.assertFalse(run.task_ids)
        self.assertFalse(run.gate_ids)
        with self.assertRaises(ValidationError):
            run.action_close_run()

    def test_advisory_version_rejects_gate_content(self):
        draft = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id, "version": "INVALID",
            "dependency_review_status": "verified", "evidence_review_status": "verified",
            "timing_review_status": "verified",
        })
        self.env["hjig.programme.template.gate"].create({
            "version_id": draft.id, "stage_id": self.stage.id,
        })
        with self.assertRaises(ValidationError):
            draft.action_submit_review()
