from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.workflow_guard import workflow_context


@tagged("post_install", "-at_install")
class TestCommercialBridge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Commercial Owner", "login": "commercial.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("new_hongyijig_custom.group_hjig_commercial_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Commercial Approver", "login": "commercial.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_commercial_user").id,
            ])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Commercial Bridge Project",
            "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "Commercial Counterparty"})
        cls.designation = cls.env["hjig.governance.designation"].create({
            "code": "COMMERCIAL-AUTH", "name": "Commercial Approval Authority", "category": "commercial",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })

    def _external_link(self, **extra):
        values = {
            "project_id": self.project.id, "ledger_side": "customer", "partner_id": self.partner.id,
            "entry_kind": "invoice", "external_reference": "CUSTOMER-INV-001",
            "external_amount": 125000.0, "owner_id": self.owner.id,
            "approval_authority_designation_id": self.designation.id,
        }
        values.update(extra)
        return self.env["hjig.commercial.link"].create(values)

    def _verify_link(self, link):
        link.with_user(self.owner).action_submit_review()
        link.approval_id.with_user(self.approver).action_approve()
        link.action_apply_decision()
        return link

    def _commercial_task(self, **extra):
        values = {
            "name": "CM-TEST: Governed Commercial Milestone",
            "project_id": self.project.id,
            "user_ids": [(6, 0, [self.owner.id])],
            "hjig_commercial_control_required": True,
            "hjig_commercial_customer_record_min": 1,
            "hjig_commercial_supplier_record_min": 0,
            "hjig_commercial_no_impact_allowed": False,
            "hjig_commercial_control_state": "draft",
            "hjig_commercial_authority_designation_id": self.designation.id,
        }
        values.update(extra)
        return self.env["project.task"].sudo().create(values)

    def test_external_ledger_link_requires_source(self):
        with self.assertRaises(ValidationError):
            self._external_link(external_reference=False)

    def test_ecn_adjustment_requires_existing_ecn_link(self):
        with self.assertRaises(ValidationError):
            self._external_link(entry_kind="ecn_adjustment")

    def test_verified_commercial_link_is_immutable(self):
        link = self._external_link()
        self.assertEqual(link.authoritative_amount, 125000.0)
        link.with_user(self.owner).action_submit_review()
        link.approval_id.with_user(self.approver).action_approve()
        link.action_apply_decision()
        self.assertEqual(link.state, "verified")
        self.assertEqual(link.approved_amount, 125000.0)
        self.assertTrue(link.approval_id.request_snapshot_hash)
        self.assertFalse(link.approval_id.request_snapshot)
        self.assertEqual(len(link.submission_ids), 1)
        self.assertIn('"ledger_side":"customer"', link.current_submission_id.snapshot)
        self.assertEqual(link.current_submission_id.snapshot_hash, link.approval_id.request_snapshot_hash)
        with self.assertRaises(ValidationError):
            link.external_amount = 130000.0
        with self.assertRaises(ValidationError):
            link.owner_id = self.approver
        with self.assertRaises(UserError):
            link.current_submission_id.unlink()

    def test_commercial_milestone_clears_only_from_existing_verified_records(self):
        link = self._verify_link(self._external_link(external_reference="CUSTOMER-INV-MILESTONE"))
        task = self._commercial_task(hjig_commercial_link_ids=[(6, 0, [link.id])])
        task.with_user(self.owner).action_submit_hjig_commercial_control()
        self.assertEqual(task.hjig_commercial_control_state, "pending")
        self.assertIn('"commercial_links":[{"entry_kind":"invoice"', task.hjig_commercial_control_approval_id.request_snapshot)
        task.hjig_commercial_control_approval_id.with_user(self.approver).action_approve()
        task.with_user(self.owner).action_apply_hjig_commercial_control()
        self.assertEqual(task.hjig_commercial_control_state, "cleared")
        self.assertTrue(task._hjig_commercial_control_is_current())
        self.assertEqual(task.hjig_commercial_controlled_by_id, self.approver)
        with self.assertRaises(ValidationError):
            task.hjig_commercial_link_ids = [(5, 0, 0)]

    def test_commercial_milestone_rejects_wrong_ledger_side(self):
        customer_link = self._verify_link(self._external_link(external_reference="CUSTOMER-WRONG-SIDE"))
        task = self._commercial_task(
            hjig_commercial_customer_record_min=0,
            hjig_commercial_supplier_record_min=1,
            hjig_commercial_link_ids=[(6, 0, [customer_link.id])],
        )
        with self.assertRaises(ValidationError):
            task.with_user(self.owner).action_submit_hjig_commercial_control()

    def test_cm10_zero_impact_requires_independent_commercial_approval(self):
        task = self._commercial_task(
            name="CM-10: Standard Zero Percent Release",
            hjig_commercial_customer_record_min=0,
            hjig_commercial_supplier_record_min=1,
            hjig_commercial_no_impact_allowed=True,
            hjig_commercial_control_outcome="no_impact",
            hjig_commercial_no_impact_reason="Standard contract has no CM-10 payment event.",
        )
        task.with_user(self.owner).action_submit_hjig_commercial_control()
        task.hjig_commercial_control_approval_id.with_user(self.approver).action_approve()
        task.with_user(self.owner).action_apply_hjig_commercial_control()
        self.assertEqual(task.hjig_commercial_control_state, "cleared")
        self.assertTrue(task._hjig_commercial_control_is_current())

    def test_rejection_applies_even_if_source_hash_changed(self):
        link = self._external_link(external_reference="CUSTOMER-INV-REJECT")
        link.with_user(self.owner).action_submit_review()
        link.approval_id.with_context(**workflow_context()).write({"request_snapshot_hash": "changed-source"})
        link.approval_id.decision_reason = "Commercial source requires correction."
        link.approval_id.with_user(self.approver).action_reject()
        link.action_apply_decision()
        self.assertEqual(link.state, "rejected")

    def test_governance_approver_without_commercial_access_cannot_decide(self):
        blind_approver = self.env["res.users"].create({
            "name": "Blind Governance Approver", "login": "blind.approver@test.invalid",
            "group_ids": [(6, 0, [
                self.env.ref("project.group_project_user").id,
                self.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        self.project.hjig_authorized_user_ids = [(4, blind_approver.id)]
        self.designation.holder_ids = [(4, blind_approver.id)]
        link = self._external_link(external_reference="CUSTOMER-INV-BLIND")
        link.with_user(self.owner).action_submit_review()
        with self.assertRaises(UserError):
            link.approval_id.with_user(blind_approver).action_approve()

    def test_submission_project_and_company_are_historical(self):
        link = self._external_link(external_reference="CUSTOMER-INV-HISTORY")
        original_project = link.project_id
        link.with_user(self.owner).action_submit_review()
        submission = link.current_submission_id
        link.approval_id.decision_reason = "Return for correction."
        link.approval_id.with_user(self.approver).action_reject()
        link.action_apply_decision()
        other_project = self.env["project.project"].create({
            "name": "Commercial Bridge Reassignment",
            "hjig_authorized_user_ids": [(6, 0, [self.owner.id, self.approver.id])],
        })
        link.project_id = other_project
        self.assertEqual(submission.project_id, original_project)
        self.assertEqual(submission.company_id, original_project.company_id)

    def test_shared_project_submission_preserves_empty_company(self):
        shared_project = self.env["project.project"].create({
            "name": "Shared Commercial Project", "company_id": False,
            "hjig_authorized_user_ids": [(6, 0, [self.owner.id, self.approver.id])],
        })
        link = self._external_link(
            project_id=shared_project.id, external_reference="CUSTOMER-INV-SHARED"
        )
        link.with_user(self.owner).action_submit_review()
        self.assertFalse(link.current_submission_id.company_id)
        self.assertEqual(link.current_submission_id.project_id, shared_project)

    def test_noncommercial_project_manager_cannot_read_financial_snapshot(self):
        manager = self.env["res.users"].create({
            "name": "Noncommercial Project Manager", "login": "noncommercial.manager@test.invalid",
            "group_ids": [(6, 0, [self.env.ref("project.group_project_manager").id])],
        })
        self.project.hjig_authorized_user_ids = [(4, manager.id)]
        link = self._external_link(external_reference="CUSTOMER-INV-MANAGER")
        link.with_user(self.owner).action_submit_review()
        with self.assertRaises(AccessError):
            self.env["hjig.commercial.link"].with_user(manager).search([("id", "=", link.id)])
        with self.assertRaises(AccessError):
            self.env["hjig.commercial.submission"].with_user(manager).search([("link_id", "=", link.id)])

    def test_project_engineer_cannot_read_commercial_snapshot(self):
        engineer = self.env["res.users"].create({
            "name": "Project Engineer Only", "login": "project.engineer.only@test.invalid",
            "group_ids": [(6, 0, [self.env.ref("project.group_project_user").id])],
        })
        self.project.hjig_authorized_user_ids = [(4, engineer.id)]
        link = self._external_link()
        link.with_user(self.owner).action_submit_review()
        with self.assertRaises(AccessError):
            self.env["hjig.commercial.submission"].with_user(engineer).search([("link_id", "=", link.id)])
        with self.assertRaises(AccessError):
            link.approval_id.with_user(engineer).read(["request_snapshot"])

    def test_commercial_source_side_kind_matrix(self):
        model = self.env["hjig.commercial.link"]
        with self.assertRaises(UserError):
            model._validate_source_profile(
                {"model": "inaccessible", "state": False, "subtype": False, "partner_type": False},
                "customer", "invoice",
            )
        model._validate_source_profile(
            {"model": "sale.order", "state": "sale", "subtype": False, "partner_type": False},
            "customer", "order",
        )
        with self.assertRaises(ValidationError):
            model._validate_source_profile(
                {"model": "sale.order", "state": "sale", "subtype": False, "partner_type": False},
                "supplier", "order",
            )
        with self.assertRaises(ValidationError):
            model._validate_source_profile(
                {"model": "account.move", "state": "draft", "subtype": "out_invoice", "partner_type": False},
                "customer", "invoice",
            )
        model._validate_source_profile(
            {"model": "account.move", "state": "posted", "subtype": "in_refund", "partner_type": False},
            "supplier", "credit_note",
        )
