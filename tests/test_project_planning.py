import hashlib
import json
from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectPlanning(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env["res.users"].create({
            "name": "Plan Owner", "login": "plan.owner@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.approver = cls.env["res.users"].create({
            "name": "Plan Approver", "login": "plan.approver@test.invalid",
            "group_ids": [(6, 0, [
                cls.env.ref("project.group_project_user").id,
                cls.env.ref("new_hongyijig_custom.group_hjig_governance_approver").id,
            ])],
        })
        cls.authority = cls.env["hjig.governance.designation"].create({
            "code": "PLAN-AUTH-TEST", "name": "Plan Approval Authority", "category": "governance",
            "holder_ids": [(6, 0, [cls.approver.id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Native Project Plan", "date_start": "2026-08-31", "date": "2026-10-30",
            "hjig_authorized_user_ids": [(6, 0, [cls.owner.id, cls.approver.id])],
        })

    def test_plan_approval_snapshots_native_tasks(self):
        task = self.env["project.task"].create({
            "name": "Design review", "project_id": self.project.id,
            "user_ids": [(6, 0, [self.owner.id])],
            "planned_date_begin": "2026-09-01 09:00:00", "date_deadline": "2026-09-03 17:00:00",
        })
        baseline = self.env["hjig.baseline"].create({
            "project_id": self.project.id, "target_ref": "project.project,%s" % self.project.id,
            "baseline_type": "plan", "revision": "R00", "effective_date": "2026-08-31",
            "approval_authority_designation_id": self.authority.id,
        })
        baseline.action_submit_review()
        self.assertEqual(baseline.state, "review")
        self.assertEqual(baseline.snapshot_json["tasks"][0]["id"], task.id)
        serialized = json.dumps(baseline.snapshot_json, sort_keys=True, separators=(",", ":"))
        self.assertEqual(baseline.snapshot_hash, hashlib.sha256(serialized.encode("utf-8")).hexdigest())

    def test_plan_readiness_blocks_missing_owner_or_dates(self):
        self.env["project.task"].create({"name": "Unplanned task", "project_id": self.project.id})
        with self.assertRaises(ValidationError):
            self.project.action_validate_hjig_plan()

    def test_working_day_schedule_skips_weekend(self):
        Run = self.env["hjig.programme.run"]
        start = datetime(2026, 9, 4, 9, 0, 0)
        self.assertEqual(Run._add_working_days(start, 1).strftime("%Y-%m-%d"), "2026-09-07")
