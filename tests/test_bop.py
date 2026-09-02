# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestBopRegister(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project_user = cls.env.ref("project.group_project_user")
        cls.owner = cls.env["res.users"].create({
            "name": "BOP Owner", "login": "bop.owner@test.invalid",
            "group_ids": [(6, 0, [project_user.id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "BOP Approver", "login": "bop.approver@test.invalid",
            "group_ids": [(6, 0, [project_user.id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "BOP Native Form Test", "x_project_code": "HJ-BOP-2026-0001",
            "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
        })
        cls.owner_designation = cls.env.ref("new_hongyijig_custom.designation_project_engineer")
        cls.approver_designation = cls.env.ref("new_hongyijig_custom.designation_project_manager")
        for designation, user in (
            (cls.owner_designation, cls.owner), (cls.approver_designation, cls.approver),
        ):
            cls.env["hjig.project.designation.assignment"].create({
                "project_id": cls.project.id,
                "designation_id": designation.id,
                "holder_ids": [(6, 0, [user.id])],
            })

    def _ready_bop(self):
        return self.env["hjig.bop"].create({
            "project_id": self.project.id,
            "revision": "R00",
            "effective_date": "2026-08-30",
            "source_route": "hongyi_guided",
            "assembly_environment_reference": "ASM-CAD-001 / R02",
            "assembly_reference_confirmed": True,
            "responsibility_boundary_ack": True,
            "change_control_ack": True,
            "customer_signoff_name": "Customer Project Authority",
            "customer_signoff_organization": "Customer Organisation",
            "customer_signoff_designation": "Project Head",
            "customer_signoff_reference": "Approved email dated 2026-08-30",
            "customer_signoff_date": "2026-08-30",
            "line_ids": [(0, 0, {
                "component_code": "BOP-001", "component_name": "Purchased Insert",
                "component_category": "insert_fastener",
                "quantity": 2, "weight_grams": 25,
                "source_ownership": "customer",
                "drawing_reference": "BOP-DWG-001",
                "drawing_revision": "R03",
                "assembly_impact": "yes",
                "impact_scope": "fitment",
                "cad_assembly_match": "confirmed",
                "datasheet_status": "received", "cad_status": "received",
                "size_status": "frozen", "sample_status": "received",
            })],
        })

    def test_bop_freeze_is_segregated_hashed_and_immutable(self):
        bop = self._ready_bop()
        self.assertEqual(bop.completion_percent, 100.0)
        bop.with_user(self.owner).action_submit_review()
        self.assertEqual(bop.state, "review")
        bop.with_user(self.approver).action_freeze()
        self.assertEqual(bop.state, "frozen")
        self.assertEqual(len(bop.snapshot_hash), 64)
        with self.assertRaises(ValidationError):
            bop.notes = "Rewrite a frozen register"

    def test_database_locked_staging_demo_allows_audited_same_user_bop_freeze(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("new_hongyijig_custom.staging_self_approval_demo", "1")
        parameters.set_param(
            "new_hongyijig_custom.staging_self_approval_database", self.env.cr.dbname
        )
        assignment = self.env["hjig.project.designation.assignment"].search([
            ("project_id", "=", self.project.id),
            ("designation_id", "=", self.approver_designation.id),
        ])
        assignment.write({"holder_ids": [(6, 0, [self.owner.id])]})
        bop = self._ready_bop()
        bop.with_user(self.owner).action_submit_review()
        bop.with_user(self.owner).action_freeze()
        self.assertEqual(bop.state, "frozen")
        reasons = self.env["hjig.transition.log"].search([
            ("target_ref", "=", "%s,%s" % (bop._name, bop.id)),
        ]).mapped("reason")
        self.assertTrue(any("STAGING TRAINING OVERRIDE" in reason for reason in reasons))

    def test_bop_cannot_submit_with_missing_physical_sample(self):
        bop = self._ready_bop()
        bop.line_ids.sample_status = "pending"
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_bop_cannot_submit_without_controlled_drawing_reference(self):
        bop = self._ready_bop()
        bop.line_ids.drawing_revision = False
        self.assertFalse(bop.stage_ready)
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_envelope_only_component_blocks_bop_freeze(self):
        bop = self._ready_bop()
        bop.line_ids.size_status = "envelope"
        self.assertFalse(bop.stage_ready)
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_customer_document_route_requires_source_document(self):
        bop = self._ready_bop()
        bop.source_route = "customer_document"
        self.assertFalse(bop.stage_ready)
        bop.source_document_url = "https://drive.google.com/file/d/test-bop-source"
        self.assertTrue(bop.stage_ready)

    def test_bop_state_cannot_be_bypassed_by_direct_write(self):
        bop = self._ready_bop()
        with self.assertRaises(ValidationError):
            bop.write({"state": "review"})
