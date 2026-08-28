from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.programme_gate_checklists import (
    GATE_FORM_EXIT_ITEMS,
    STAGE_MASTER_GATE_ARTIFACTS,
    _checklist_evidence_artifact_code,
    _explicit_evidence_artifact_code,
)


@tagged("post_install", "-at_install")
class TestProgrammeTemplateGovernance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner_user = cls.env["res.users"].create({
            "name": "Programme Owner",
            "login": "programme.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver_user = cls.env["res.users"].create({
            "name": "Programme Approver",
            "login": "programme.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_document_controller").id,
            ])],
        })
        cls.owner_designation = cls.env["hjig.governance.designation"].create({
            "code": "PROGRAMME-OWNER-TEST",
            "name": "Programme Owner Test",
            "category": "project",
            "holder_ids": [(6, 0, [cls.owner_user.id])],
        })
        cls.approver_designation = cls.env["hjig.governance.designation"].create({
            "code": "PROGRAMME-APPROVER-TEST",
            "name": "Programme Approver Test",
            "category": "governance",
            "holder_ids": [(6, 0, [cls.approver_user.id])],
        })
        cls.stage = cls.env["hjig.launchguard.stage"].create({
            "code": "PG-TEST",
            "name": "Programme Test Gate",
            "sequence": 10,
            "stage_type": "technical_gate",
        })
        cls.artifact = cls.env["hjig.governance.artifact.master"].create({
            "code": "PG-FRM-TEST",
            "name": "Programme Test Form",
            "artifact_type": "form",
            "applicable_stage_ids": [(6, 0, [cls.stage.id])],
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "default_register_type": "programme_internal",
            "default_document_class": "project_working",
            "revision": "1.0",
        })
        cls.template = cls.env["hjig.programme.template"].create({
            "code": "PGT",
            "name": "Programme Governance Test",
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
        })
        cls.version = cls.env["hjig.programme.template.version"].create({
            "template_id": cls.template.id,
            "version": "1.0",
            "effective_from": "2026-08-27",
            "legacy_source_database": "legacy_test_db",
            "legacy_source_project_id": 99,
            "legacy_source_task_count": 2,
            "dependency_review_status": "verified",
            "evidence_review_status": "verified",
        })
        cls.gate = cls.env["hjig.programme.template.gate"].create({
            "version_id": cls.version.id,
            "stage_id": cls.stage.id,
            "sequence": 10,
        })
        cls.activity_1 = cls.env["hjig.programme.template.activity"].create({
            "version_id": cls.version.id,
            "code": "ACT-001",
            "name": "First Governed Activity",
            "sequence": 10,
            "gate_line_id": cls.gate.id,
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "required_artifact_ids": [(6, 0, [cls.artifact.id])],
            "legacy_source_task_id": 1001,
            "legacy_source_stage_id": 501,
            "legacy_source_stage_name": "Legacy Test Gate",
        })
        cls.activity_2 = cls.env["hjig.programme.template.activity"].create({
            "version_id": cls.version.id,
            "code": "ACT-002",
            "name": "Dependent Governed Activity",
            "sequence": 20,
            "gate_line_id": cls.gate.id,
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "predecessor_ids": [(6, 0, [cls.activity_1.id])],
            "legacy_source_task_id": 1002,
            "legacy_source_stage_id": 501,
            "legacy_source_stage_name": "Legacy Test Gate",
        })
        cls.artifact_rule = cls.env["hjig.programme.template.artifact"].create({
            "version_id": cls.version.id,
            "artifact_master_id": cls.artifact.id,
            "stage_id": cls.stage.id,
            "mandatory": True,
        })
        cls.dependency_rule = cls.env["hjig.programme.template.dependency.rule"].create({
            "version_id": cls.version.id,
            "legacy_source_rule_id": 9001,
            "predecessor_activity_id": cls.activity_1.id,
            "successor_activity_id": cls.activity_2.id,
            "predecessor_basis": "project",
            "successor_basis": "project",
            "rule_type": "a1",
            "scope_matching_rule": "PROJECT->PROJECT",
            "aggregation_requirement": "Single predecessor",
        })
        cls.checklist_template_item = cls.env["hjig.programme.template.checklist.item"].create({
            "version_id": cls.version.id,
            "gate_line_id": cls.gate.id,
            "code": "PG-CHECK-001",
            "sequence": 10,
            "subhead": "governance",
            "item_text": "Governed test checklist requirement",
            "mandatory": True,
            "evidence_required": False,
            "execution_basis": "project",
            "linked_activity_id": cls.activity_1.id,
            "owner_designation_id": cls.owner_designation.id,
            "approver_designation_id": cls.approver_designation.id,
            "source_reference": "Test authority",
            "source_version": "1.0",
        })
        cls.version.action_submit_review()
        cls.version.with_user(cls.approver_user).action_approve()
        cls.partner = cls.env["res.partner"].create({"name": "Programme Test Customer"})

    def _sale_order(self, **overrides):
        values = {
            "partner_id": self.partner.id,
            "state": "sale",
            "hjig_programme_version_id": self.version.id,
            "hjig_project_code": "HJ-PGT-2026-0001",
            "hjig_order_punch_pdf_url": "https://drive.google.com/file/d/order-punch-test/view",
            "hjig_commercial_pdf_url": "https://drive.google.com/file/d/commercial-test/view",
        }
        values.update(overrides)
        return self.env["sale.order"].create(values)

    def test_approved_version_is_hashed_and_frozen(self):
        self.assertEqual(self.version.state, "approved")
        self.assertTrue(self.version.is_current)
        self.assertEqual(len(self.version.definition_hash), 64)
        self.assertEqual(self.version.legacy_source_task_count, 2)
        with self.assertRaises(ValidationError):
            self.activity_1.name = "Rewritten activity"
        with self.assertRaises(ValidationError):
            self.version.version = "2.0"
        with self.assertRaises(ValidationError):
            self.activity_1.unlink()

    def test_template_opens_versions_as_full_records(self):
        action = self.template.action_open_versions()
        self.assertEqual(action["res_model"], "hjig.programme.template.version")
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("template_id", "=", self.template.id)])

    def test_pending_checklist_content_blocks_governed_review(self):
        draft = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id,
            "version": "PENDING-CONTENT",
            "dependency_review_status": "verified",
            "evidence_review_status": "verified",
        })
        gate = self.env["hjig.programme.template.gate"].create({
            "version_id": draft.id,
            "stage_id": self.stage.id,
        })
        self.env["hjig.programme.template.activity"].create({
            "version_id": draft.id,
            "code": "PENDING-ACT-001",
            "name": "Session activity — PENDING CHECKLIST CONTENT",
            "gate_line_id": gate.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        self.env["hjig.programme.template.artifact"].create({
            "version_id": draft.id,
            "artifact_master_id": self.artifact.id,
            "stage_id": self.stage.id,
            "mandatory": True,
        })
        with self.assertRaises(ValidationError):
            draft.action_submit_review()

    def test_approval_requires_designation_holder(self):
        version = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id,
            "version": "2.0",
            "effective_from": "2026-09-01",
            "dependency_review_status": "verified",
            "evidence_review_status": "verified",
        })
        gate = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id,
            "stage_id": self.stage.id,
        })
        self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "V2-ACT-001",
            "name": "Version Two Activity",
            "gate_line_id": gate.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        self.env["hjig.programme.template.artifact"].create({
            "version_id": version.id,
            "artifact_master_id": self.artifact.id,
            "stage_id": self.stage.id,
            "mandatory": True,
        })
        self.env["hjig.programme.template.checklist.item"].create({
            "version_id": version.id,
            "gate_line_id": gate.id,
            "code": "V2-CHECK-001",
            "subhead": "governance",
            "item_text": "Version two governed checklist",
            "mandatory": True,
            "evidence_required": False,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "source_reference": "Test authority",
            "source_version": "1.0",
        })
        version.action_submit_review()
        with self.assertRaises(UserError):
            version.with_user(self.owner_user).action_approve()

    def test_order_activation_is_idempotent_and_generates_snapshot(self):
        order = self._sale_order()
        order.action_activate_hjig_programme()
        run = order.hjig_programme_run_id
        self.assertTrue(run)
        self.assertEqual(run.state, "generated")
        self.assertEqual(run.template_version_id, self.version)
        self.assertEqual(run.definition_hash, self.version.definition_hash)
        self.assertEqual(len(run.task_ids), 2)
        self.assertEqual(len(run.artifact_requirement_ids), 1)
        self.assertEqual(len(run.checklist_instance_ids), 1)
        dependent = run.task_ids.filtered(lambda task: task.hjig_template_activity_id == self.activity_2)
        first = run.task_ids.filtered(lambda task: task.hjig_template_activity_id == self.activity_1)
        self.assertEqual(dependent.depend_on_ids, first)
        order.action_activate_hjig_programme()
        self.assertEqual(
            self.env["hjig.programme.run"].search_count([("sale_order_id", "=", order.id)]), 1
        )
        self.assertEqual(
            self.env["project.task"].search_count([("hjig_programme_run_id", "=", run.id)]), 2
        )

    def test_generated_snapshot_cannot_be_repointed_or_deleted(self):
        order = self._sale_order(hjig_project_code="HJ-PGT-2026-0002")
        order.action_activate_hjig_programme()
        run = order.hjig_programme_run_id
        with self.assertRaises(ValidationError):
            run.template_version_id = False
        with self.assertRaises(UserError):
            run.unlink()

    def test_unapproved_version_cannot_activate_order(self):
        draft = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id,
            "version": "DRAFT",
        })
        order = self._sale_order(
            hjig_programme_version_id=draft.id,
            hjig_project_code="HJ-PGT-2026-0003",
        )
        with self.assertRaises(ValidationError):
            order.action_activate_hjig_programme()

    def test_artifact_rule_must_use_approved_stage(self):
        other_stage = self.env["hjig.launchguard.stage"].create({
            "code": "PG-OTHER",
            "name": "Other Programme Gate",
            "sequence": 20,
            "stage_type": "technical_gate",
        })
        draft = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id,
            "version": "ARTIFACT-CHECK",
        })
        with self.assertRaises(ValidationError):
            self.env["hjig.programme.template.artifact"].create({
                "version_id": draft.id,
                "artifact_master_id": self.artifact.id,
                "stage_id": other_stage.id,
            })

    def test_review_rejects_unverified_dependency_map(self):
        draft = self.env["hjig.programme.template.version"].create({
            "template_id": self.template.id,
            "version": "UNVERIFIED",
            "evidence_review_status": "verified",
        })
        gate = self.env["hjig.programme.template.gate"].create({
            "version_id": draft.id, "stage_id": self.stage.id,
        })
        self.env["hjig.programme.template.activity"].create({
            "version_id": draft.id, "code": "UNVERIFIED-1", "name": "Unverified Activity",
            "gate_line_id": gate.id, "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        with self.assertRaises(ValidationError):
            draft.action_submit_review()

    def test_sourcebridge_supports_multiple_components_per_programme(self):
        order = self._sale_order(hjig_project_code="HJ-PGT-2026-0004")
        order.action_activate_hjig_programme()
        run = order.hjig_programme_run_id
        engagement = self.env["hjig.sourcebridge.engagement"].create({
            "code": "SB-PGT-0001", "name": "Two Components", "project_id": run.project_id.id,
            "programme_run_id": run.id, "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        for code in ("COMP-01", "COMP-02"):
            self.env["hjig.sourcebridge.component"].create({
                "engagement_id": engagement.id, "code": code, "name": code,
                "category": "bought_out", "quantity": 1, "specification": "Approved specification",
            })
        self.assertEqual(len(engagement.component_ids), 2)
        engagement.with_user(self.approver_user).action_activate()
        self.assertEqual(engagement.state, "active")

    def test_gate_cannot_approve_without_completed_tasks_and_documents(self):
        order = self._sale_order(hjig_project_code="HJ-PGT-2026-0005")
        order.action_activate_hjig_programme()
        gate = order.hjig_programme_run_id.gate_ids[:1]
        gate.action_refresh_readiness()
        self.assertEqual(gate.state, "blocked")
        with self.assertRaises(ValidationError):
            gate.with_user(self.approver_user).action_approve_gate()

    def test_checklist_result_requires_owner_designation_and_governed_action(self):
        order = self._sale_order(hjig_project_code="HJ-PGT-2026-0006")
        order.action_activate_hjig_programme()
        item = order.hjig_programme_run_id.checklist_instance_ids
        with self.assertRaises(ValidationError):
            item.status = "pass"
        with self.assertRaises(UserError):
            item.with_user(self.approver_user).action_mark_pass()
        item.with_user(self.owner_user).action_mark_pass()
        self.assertEqual(item.status, "pass")
        self.assertEqual(item.ticked_by_id, self.owner_user)

    def test_nonconditional_checklist_item_cannot_be_na(self):
        order = self._sale_order(hjig_project_code="HJ-PGT-2026-0007")
        order.action_activate_hjig_programme()
        item = order.hjig_programme_run_id.checklist_instance_ids
        item.remarks = "Not applicable request"
        with self.assertRaises(ValidationError):
            item.with_user(self.approver_user).action_mark_na()

    def test_mould_gate_and_checklist_instances_sync_per_approved_mould(self):
        template = self.env["hjig.programme.template"].create({
            "code": "PMT",
            "name": "Per Mould Test",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        version = self.env["hjig.programme.template.version"].create({
            "template_id": template.id,
            "version": "1.0",
            "effective_from": "2026-08-28",
            "dependency_review_status": "verified",
            "evidence_review_status": "verified",
        })
        gate = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id,
            "stage_id": self.stage.id,
            "execution_basis": "mould",
        })
        activity = self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "PMT-A01",
            "name": "Per mould controlled activity",
            "gate_line_id": gate.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "execution_basis": "mould",
        })
        component_activity = self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "PMT-A02",
            "name": "Per component controlled activity",
            "sequence": 20,
            "gate_line_id": gate.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "execution_basis": "component",
            "predecessor_ids": [(6, 0, [activity.id])],
        })
        self.env["hjig.programme.template.artifact"].create({
            "version_id": version.id,
            "artifact_master_id": self.artifact.id,
            "stage_id": self.stage.id,
            "mandatory": True,
        })
        self.env["hjig.programme.template.checklist.item"].create({
            "version_id": version.id,
            "gate_line_id": gate.id,
            "code": "PMT-CHECK-01",
            "subhead": "technical",
            "item_text": "Per-mould evidence is complete",
            "mandatory": True,
            "evidence_required": False,
            "execution_basis": "mould",
            "linked_activity_id": activity.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "source_reference": "Checklist Model Specification v2",
            "source_version": "v2",
        })
        version.action_submit_review()
        version.with_user(self.approver_user).action_approve()

        order = self._sale_order(
            hjig_programme_version_id=version.id,
            hjig_project_code="HJ-PMT-2026-0001",
        )
        project = self.env["project.project"].create({
            "name": "Per Mould Project",
            "x_project_code": "HJ-PMT-2026-0001",
            "hjig_project_record_type": "customer",
        })
        run = self.env["hjig.programme.run"].create({
            "name": "HJ-PMT-2026-0001 — Per Mould Test",
            "sale_order_id": order.id,
            "project_id": project.id,
            "template_version_id": version.id,
        })

        def approved_mould(number):
            mould = self.env["x_mould"].create({
                "x_name": number,
                "x_project_id": project.id,
                "x_mould_number": number,
                "x_owner_designation_id": self.owner_designation.id,
                "x_approver_designation_id": self.approver_designation.id,
            })
            part = self.env["x_mould_part"].create({
                "x_name": "%s Part" % number,
                "x_mould_id": mould.id,
                "x_part_number": "%s-P01" % number,
            })
            mould.with_context(allow_native_form_workflow=True).write({
                "x_workflow_state": "approved",
                "x_mould_planning_status": "final_locked",
            })
            return mould, part

        mould_1, part_1 = approved_mould("M-001")
        run.action_generate_execution()
        self.assertEqual(run.gate_ids.mould_id, mould_1)
        self.assertEqual(run.checklist_instance_ids.mould_id, mould_1)
        self.assertEqual(run.artifact_requirement_ids.mould_id, mould_1)
        self.assertEqual(len(run.task_ids), 2)
        mould_task_1 = run.task_ids.filtered(
            lambda task: task.hjig_template_activity_id == activity
        )
        component_task_1 = run.task_ids.filtered(
            lambda task: task.hjig_template_activity_id == component_activity
        )
        self.assertEqual(mould_task_1.hjig_mould_id, mould_1)
        self.assertEqual(component_task_1.hjig_part_id, part_1)
        self.assertEqual(component_task_1.depend_on_ids, mould_task_1)

        mould_2, part_2 = approved_mould("M-002")
        run.action_sync_mould_execution()
        self.assertEqual(set(run.gate_ids.mapped("mould_id").ids), {mould_1.id, mould_2.id})
        self.assertEqual(len(run.checklist_instance_ids), 2)
        self.assertEqual(len(run.artifact_requirement_ids), 2)
        self.assertEqual(len(run.task_ids), 4)
        component_task_2 = run.task_ids.filtered(lambda task: task.hjig_part_id == part_2)
        mould_task_2 = run.task_ids.filtered(
            lambda task: task.hjig_template_activity_id == activity and task.hjig_mould_id == mould_2
        )
        self.assertEqual(component_task_2.depend_on_ids, mould_task_2)

    def test_conditional_activity_requires_designation_scope_decision(self):
        template = self.env["hjig.programme.template"].create({
            "code": "CND",
            "name": "Conditional Programme Test",
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
        })
        version = self.env["hjig.programme.template.version"].create({
            "template_id": template.id,
            "version": "1.0",
            "effective_from": "2026-08-28",
            "dependency_review_status": "verified",
            "evidence_review_status": "verified",
        })
        gate = self.env["hjig.programme.template.gate"].create({
            "version_id": version.id, "stage_id": self.stage.id,
        })
        activity = self.env["hjig.programme.template.activity"].create({
            "version_id": version.id,
            "code": "CND-A01",
            "name": "Conditional Moldflow Review",
            "gate_line_id": gate.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "conditional": True,
        })
        self.env["hjig.programme.template.artifact"].create({
            "version_id": version.id,
            "artifact_master_id": self.artifact.id,
            "stage_id": self.stage.id,
        })
        self.env["hjig.programme.template.checklist.item"].create({
            "version_id": version.id,
            "gate_line_id": gate.id,
            "code": "CND-CHECK-01",
            "subhead": "technical",
            "item_text": "Conditional scope is governed",
            "evidence_required": False,
            "linked_activity_id": activity.id,
            "owner_designation_id": self.owner_designation.id,
            "approver_designation_id": self.approver_designation.id,
            "source_reference": "Test authority",
            "source_version": "1.0",
        })
        version.action_submit_review()
        version.with_user(self.approver_user).action_approve()
        order = self._sale_order(
            hjig_programme_version_id=version.id,
            hjig_project_code="HJ-CND-2026-0001",
        )
        order.action_activate_hjig_programme()
        run = order.hjig_programme_run_id
        self.assertEqual(run.state, "draft")
        self.assertEqual(len(run.scope_decision_ids), 1)
        self.assertFalse(run.task_ids)
        with self.assertRaises(ValidationError):
            run.action_generate_execution()
        run.scope_decision_ids.with_user(self.owner_user).write({
            "decision": "exclude", "reason": "Moldflow is not required for this project scope.",
        })
        run.action_generate_execution()
        self.assertEqual(run.state, "generated")
        self.assertFalse(run.task_ids)

    def test_explicit_checklist_evidence_mapping_is_stage_valid(self):
        Artifact = self.env["hjig.governance.artifact.master"]
        Stage = self.env["hjig.launchguard.stage"]
        for stage_code, _row_number, text in GATE_FORM_EXIT_ITEMS:
            artifact_code = _explicit_evidence_artifact_code(stage_code, text)
            if not artifact_code:
                continue
            artifact = Artifact.search([("code", "=", artifact_code)], limit=1)
            stage = Stage.search([("code", "=", stage_code)], limit=1)
            self.assertTrue(artifact, "%s is not a governed artifact" % artifact_code)
            self.assertIn(
                stage,
                artifact.applicable_stage_ids,
                "%s is not valid for %s" % (artifact_code, stage_code),
            )

    def test_every_authoritative_checklist_has_stage_valid_evidence_type(self):
        Artifact = self.env["hjig.governance.artifact.master"]
        Stage = self.env["hjig.launchguard.stage"]
        for stage_code, _row_number, text in GATE_FORM_EXIT_ITEMS:
            artifact_code = _checklist_evidence_artifact_code(stage_code, text)
            self.assertTrue(artifact_code, "%s has no governed evidence type" % stage_code)
            artifact = Artifact.search([("code", "=", artifact_code)], limit=1)
            stage = Stage.search([("code", "=", stage_code)], limit=1)
            self.assertTrue(artifact, "%s is not a governed artifact" % artifact_code)
            self.assertIn(stage, artifact.applicable_stage_ids)

        self.assertEqual(STAGE_MASTER_GATE_ARTIFACTS["TG-04"], "FRM-B5-G01")
        self.assertEqual(STAGE_MASTER_GATE_ARTIFACTS["PA-00"], "FRM-B1-G01")
