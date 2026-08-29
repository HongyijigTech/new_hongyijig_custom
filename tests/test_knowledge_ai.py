from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestKnowledgeAi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Knowledge Owner", "login": "knowledge.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Knowledge Approver", "login": "knowledge.approver@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id, cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Knowledge Project", "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
        })
        cls.reviewer_role = cls.env["hjig.governance.designation"].create({
            "code": "KB-REVIEWER", "name": "Knowledge Reviewer", "category": "engineering",
            "holder_ids": [(6, 0, [cls.owner.id])],
        })
        cls.approver_role = cls.env["hjig.governance.designation"].create({
            "code": "KB-APPROVER", "name": "Knowledge Approver", "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })

    def _knowledge(self):
        return self.env["hjig.knowledge.item"].create({
            "project_id": self.project.id, "code": "STEEL-P20", "title": "P20 Tool Steel",
            "category": "tool_steel", "version": "1.0", "applicability": "General mould base and core applications subject to engineering approval.",
            "controlled_content": "<p>Controlled engineering reference.</p>",
            "source_standard": "Approved manufacturer data sheet", "effective_date": "2026-08-29",
            "owner_id": self.owner.id, "reviewer_designation_id": self.reviewer_role.id,
            "approver_designation_id": self.approver_role.id,
        })

    def test_only_approved_knowledge_is_authoritative_for_ai(self):
        item = self._knowledge()
        values = {
            "project_id": self.project.id, "target_ref": "project.project,%s" % self.project.id,
            "capability": "retrieve", "model_identity": "test-model", "permission_scope": "Project technical data",
            "output_summary": "P20 reference retrieved.", "knowledge_source_ids": [(6, 0, [item.id])],
            "confidence": 90,
        }
        log = self.env["hjig.ai.assistance.log"]._log_assistance(values)
        self.assertFalse(log.authoritative)
        item.with_user(self.owner).action_submit_review()
        item.approval_id.with_user(self.approver).action_approve()
        item.action_apply_decision()
        self.assertEqual(item.state, "approved")
        log.invalidate_recordset(["authoritative"])
        self.assertTrue(log.authoritative)

    def test_users_cannot_fabricate_ai_provenance(self):
        with self.assertRaises(UserError):
            self.env["hjig.ai.assistance.log"].create({
                "project_id": self.project.id, "target_ref": "project.project,%s" % self.project.id,
                "capability": "draft", "model_identity": "fake", "permission_scope": "none",
                "output_summary": "Fabricated", "confidence": 100,
            })

    def test_non_reviewer_cannot_submit_knowledge(self):
        outsider = self.env["res.users"].create({
            "name": "Knowledge Outsider", "login": "knowledge.outsider@test.invalid",
            "group_ids": [(6, 0, [self.env.ref("project.group_project_user").id])],
        })
        self.project.hjig_authorized_user_ids = [(4, outsider.id)]
        with self.assertRaises(UserError):
            self._knowledge().with_user(outsider).action_submit_review()
