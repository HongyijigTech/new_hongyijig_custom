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
        bop = self.env["hjig.bop"].create({
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
            "population_declared_complete": True,
            "population_coordinator_designation": "Project Coordinator",
            "population_unresolved_count": 0,
            "population_evidence_reference": "Customer BOM v3 + SOR R01",
            "population_technical_reviewed": True,
            "population_technical_reviewer_designation": "Senior Tool Design Engineer",
            "population_customer_signed": True,
            "population_customer_reference": "Customer email 2026-08-30",
            "design_release_baseline": "BOP-R00 + SOR-R01 + MP-R00",
            "design_release_recipients": "Design Agency; Tooling Agency",
            "design_freeze_customer_confirmed": True,
            "design_freeze_customer_reference": "Customer design-freeze email 2026-08-30",
            "design_freeze_internal_approver": "Senior Tool Design Engineer",
            "line_ids": [(0, 0, {
                "component_code": "BOP-001", "component_name": "Purchased Insert",
                "component_category": "insert_fastener",
                "quantity": 2, "weight_grams": 25,
                "manufacturer": "Approved Manufacturer", "model_part_number": "INS-001",
                "item_revision": "R03", "sourcing_responsibility": "customer_supplied",
                "drawing_2d_status": "available", "drawing_2d_reference": "BOP-DWG-001",
                "drawing_2d_revision": "R03", "model_3d_status": "available",
                "model_3d_reference": "BOP-CAD-001", "model_3d_revision": "R03",
                "datasheet_reference": "BOP-DS-001", "datasheet_revision": "R03",
                "technical_validation": "validated",
                "validator_designation": "Senior Tool Design Engineer",
                "required_quantity": 2, "ordered_quantity": 2,
                "received_quantity": 2, "verified_usable_quantity": 2,
                "customer_item_freeze": True,
                "customer_item_freeze_reference": "Customer email 2026-08-30",
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
        component = self.env["hjig.bop.product.component"].create({
            "bop_id": bop.id, "code": "PC-001", "name": "Moulded Housing",
            "maturity": "confirmed",
        })
        mapping = self.env["hjig.bop.mapping"].create({
            "bop_id": bop.id, "code": "MAP-001", "bop_line_id": bop.line_ids.id,
            "topology": "single", "maturity": "tentative", "accountable_designation": "Project Coordinator",
            "due_date": "2026-08-30", "evidence_reference": "Interface drawing INT-001 R01",
            "technical_confirmed": True, "customer_signed": True,
            "customer_reference": "Customer mapping email 2026-08-30",
            "participant_ids": [(0, 0, {"component_id": component.id, "role": "primary_mount"})],
        })
        mapping.maturity = "confirmed"
        bop.line_ids.action_lock_item()
        bop.action_generate_design_release()
        return bop

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

    def test_bop_cannot_submit_with_insufficient_verified_quantity(self):
        bop = self._ready_bop()
        bop.line_ids.with_context(hjig_bop_item_workflow=True).write({"lock_status": "draft"})
        bop.line_ids.verified_usable_quantity = 0
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_bop_cannot_submit_without_controlled_2d_revision(self):
        bop = self._ready_bop()
        bop.line_ids.with_context(hjig_bop_item_workflow=True).write({"lock_status": "draft"})
        bop.line_ids.drawing_2d_revision = False
        self.assertFalse(bop.stage_ready)
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_unlocked_item_blocks_design_release(self):
        bop = self._ready_bop()
        bop.line_ids.with_context(hjig_bop_item_workflow=True).write({"lock_status": "draft"})
        self.assertFalse(bop.design_release_ready)
        with self.assertRaises(ValidationError):
            bop.action_generate_design_release()

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

    def test_interface_mapping_requires_two_participants_and_meeting_flag(self):
        bop = self._ready_bop()
        second = self.env["hjig.bop.product.component"].create({
            "bop_id": bop.id, "code": "PC-002", "name": "Adjacent Bonnet",
            "maturity": "confirmed", "is_meeting_component": True,
        })
        mapping = self.env["hjig.bop.mapping"].create({
            "bop_id": bop.id, "code": "MAP-002", "bop_line_id": bop.line_ids.id,
            "topology": "interface", "maturity": "tentative",
        })
        mapping.write({"participant_ids": [
            (0, 0, {"component_id": bop.product_component_ids[0].id, "role": "primary_mount"}),
            (0, 0, {"component_id": second.id, "role": "adjacent_meeting"}),
        ]})
        mapping.write({
            "maturity": "confirmed", "technical_confirmed": True, "customer_signed": True,
            "customer_reference": "Customer approved", "evidence_reference": "INT-002",
            "accountable_designation": "Senior Tool Design Engineer", "due_date": "2026-09-01",
        })
        self.assertTrue(mapping.is_confirmed_ready)

    def test_mapping_change_invalidates_design_release(self):
        bop = self._ready_bop()
        self.assertTrue(bop.design_release_valid)
        bop.mapping_ids.evidence_reference = "Revised interface evidence"
        self.assertFalse(bop.design_release_valid)
