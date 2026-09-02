from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "risk_copilot")
class TestRiskCopilot(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "Risk Copilot User", "login": "risk.copilot@test.invalid",
            "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
        })
        cls.project = cls.env["project.project"].create({
            "name": "Risk Copilot Test", "hjig_project_record_type": "customer",
            "x_project_code": "HJ-AI-RISK-TEST",
            "hjig_authorized_user_ids": [(6, 0, [cls.user.id])],
        })

    def _suggestion(self):
        scan = self.env["hjig.risk.ai.scan"].create({"project_id": self.project.id})
        suggestion = self.env["hjig.risk.ai.suggestion"].create({
            "scan_id": scan.id, "source_type": "bop", "source_reference": "BOP-TEST / MOTOR-01",
            "evidence_excerpt": "Supplier status is not identified", "cause": "Motor supplier is not frozen",
            "description": "Motor envelope may change after housing design starts",
            "impact_statement": "Housing redesign and tooling delay", "category": "supplier",
            "probability": "4", "impact": "5", "mitigation_plan": "Freeze supplier and drawing",
            "preventive_action": "Review BOP before design release", "contingency_plan": "Hold IG-01",
            "trigger_indicator": "Supplier remains open", "confidence": 91,
        })
        scan.state = "review"
        return scan, suggestion

    def test_missing_provider_configuration_fails_closed(self):
        scan = self.env["hjig.risk.ai.scan"].create({"project_id": self.project.id})
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("hjig.ai.claude_api_key", "")
        parameters.set_param("hjig.ai.claude_model", "")
        with patch.dict("os.environ", {"HJIG_CLAUDE_API_KEY": "", "HJIG_CLAUDE_MODEL": ""}, clear=False):
            with self.assertRaises(UserError):
                scan.action_run_scan()
        self.assertEqual(scan.state, "draft")

    def test_employee_must_review_every_suggestion(self):
        scan, suggestion = self._suggestion()
        scan.employee_additional_risks_confirmed = True
        with self.assertRaises(ValidationError):
            scan.action_complete_review()
        suggestion.disposition_note = "Unsupported by current controlled evidence"
        suggestion.action_reject()
        scan.action_complete_review()
        self.assertEqual(scan.state, "complete")
        self.assertEqual(scan.reviewed_by_id, self.env.user)

    def test_accepted_suggestion_creates_controlled_draft_risk(self):
        scan, suggestion = self._suggestion()
        suggestion.action_add_to_register()
        self.assertEqual(suggestion.disposition, "applied")
        self.assertTrue(suggestion.risk_id)
        self.assertEqual(suggestion.risk_id.project_id, self.project)
        self.assertEqual(suggestion.risk_id.source_type, "bop")
        self.assertEqual(suggestion.risk_id.status, "open")
        self.assertEqual(suggestion.risk_id.risk_score, 20)
