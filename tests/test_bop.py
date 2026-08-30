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
            "name": "BOP Native Form Test", "x_project_code": "HJ-BOP-TEST-0001",
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
            "customer_signoff_name": "Customer Project Authority",
            "customer_signoff_designation": "Project Head",
            "customer_signoff_date": "2026-08-30",
            "line_ids": [(0, 0, {
                "component_code": "BOP-001", "component_name": "Purchased Insert",
                "quantity": 2, "weight_grams": 25,
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

    def test_bop_cannot_submit_with_missing_physical_sample(self):
        bop = self._ready_bop()
        bop.line_ids.sample_status = "pending"
        with self.assertRaises(ValidationError):
            bop.with_user(self.owner).action_submit_review()

    def test_bop_state_cannot_be_bypassed_by_direct_write(self):
        bop = self._ready_bop()
        with self.assertRaises(ValidationError):
            bop.write({"state": "review"})
