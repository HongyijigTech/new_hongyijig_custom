# -*- coding: utf-8 -*-

import hashlib
import json
import os

import requests
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


RISK_CATEGORIES = [
    ("technical", "Technical"), ("quality", "Quality"), ("resource", "Resource"),
    ("schedule", "Schedule"), ("commercial", "Commercial"), ("supplier", "Supplier"),
    ("customer", "Customer"), ("other", "Other"),
]

SCORE_SELECTION = [(str(value), str(value)) for value in range(1, 6)]


class HjigTargetMixin(models.AbstractModel):
    _inherit = "hjig.target.mixin"

    @api.model
    def _selection_target_model(self):
        return super()._selection_target_model() + [
            ("hjig.risk.ai.scan", "AI Risk Review"),
            ("hjig.risk.ai.suggestion", "AI Risk Suggestion"),
        ]


class HjigRiskAiScan(models.Model):
    _name = "hjig.risk.ai.scan"
    _description = "Governed AI Risk Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "run_date desc, id desc"
    _rec_name = "code"

    code = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True, index=True)
    origin_requirement_id = fields.Many2one(
        "hjig.programme.run.artifact", string="IG / Gate Requirement", ondelete="set null", index=True,
        domain="[('project_id', '=', project_id), ('artifact_code', '=', 'FRM-006')]",
    )
    stage_id = fields.Many2one(related="origin_requirement_id.stage_id", store=True, readonly=True)
    scope_note = fields.Text(
        default="Review the latest SOR, BOP, mould planning, design assumptions and current Risk Register.",
        required=True,
    )
    source_snapshot_hash = fields.Char(readonly=True, copy=False, index=True)
    source_snapshot_summary = fields.Text(readonly=True, copy=False)
    prompt_version = fields.Char(default="HJIG-IG-RISK-1.0", required=True, readonly=True)
    model_identity = fields.Char(readonly=True, copy=False)
    run_date = fields.Datetime(readonly=True, copy=False)
    run_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Ready to Scan"), ("review", "Employee Review"), ("complete", "Review Complete"), ("failed", "Scan Failed")],
        default="draft", required=True, readonly=True, copy=False, index=True, tracking=True,
    )
    suggestion_ids = fields.One2many("hjig.risk.ai.suggestion", "scan_id", string="AI Draft Risks")
    suggestion_count = fields.Integer(compute="_compute_counts")
    pending_count = fields.Integer(compute="_compute_counts")
    applied_count = fields.Integer(compute="_compute_counts")
    employee_additional_risks_confirmed = fields.Boolean(
        string="Employee checked for additional risks", tracking=True,
        help="Confirms that the employee considered risks not found by AI and added them directly to the Risk Register.",
    )
    review_notes = fields.Text(tracking=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)
    failure_message = fields.Text(readonly=True, copy=False)

    _code_unique = models.Constraint("UNIQUE(code)", "AI Risk Review code must be unique.")

    @api.depends("suggestion_ids.disposition")
    def _compute_counts(self):
        for scan in self:
            scan.suggestion_count = len(scan.suggestion_ids)
            scan.pending_count = len(scan.suggestion_ids.filtered(lambda item: item.disposition == "pending"))
            scan.applied_count = len(scan.suggestion_ids.filtered(lambda item: item.disposition in ("applied", "merged")))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = sequence.next_by_code("hjig.risk.ai.scan") or _("New")
        return super().create(vals_list)

    def _plain(self, record, field_names):
        result = {}
        for name in field_names:
            if name not in record._fields:
                continue
            value = record[name]
            field = record._fields[name]
            if field.type == "many2one":
                value = value.display_name if value else False
            elif field.type in ("one2many", "many2many", "binary"):
                continue
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            result[name] = value
        return result

    def _source_snapshot(self):
        self.ensure_one()
        sor = self.env["hjig.sor"].search([("project_id", "=", self.project_id.id)], order="id desc", limit=1)
        bop = self.env["hjig.bop"].search([("project_id", "=", self.project_id.id)], order="id desc", limit=1)
        moulds = self.env["x_mould"].search([("x_project_id", "=", self.project_id.id)], order="id")
        existing = self.env["hjig.project.risk"].search([("project_id", "=", self.project_id.id)], order="id")
        snapshot = {
            "project": self._plain(self.project_id, ["name", "x_project_code", "partner_id"]),
            "gate": self.stage_id.display_name if self.stage_id else "IG-01 / current gate",
            "employee_scope_note": self.scope_note,
            "sor": self._plain(sor, ["code", "industry", "intake_route", "state", "open_clarification_count"]) if sor else None,
            "sor_requirements": [self._plain(line, [
                "requirement_id", "section_title", "category", "requirement_text", "customer_declaration",
                "declaration_state", "source_reference", "acceptance_criteria", "priority", "notes",
            ]) for line in sor.requirement_ids[:300]] if sor else [],
            "bop": self._plain(bop, [
                "code", "revision", "state", "source_route", "assembly_environment_reference",
                "population_unresolved_count", "population_ready", "mapping_ready", "design_release_ready", "governance_blockers",
            ]) if bop else None,
            "bop_lines": [self._plain(line, [
                "component_code", "component_name", "customer_part_number", "manufacturer", "model_part_number",
                "component_category", "quantity", "supplier_reference", "supplier_status", "drawing_reference",
                "drawing_revision", "assembly_impact", "impact_scope", "impact_description", "cad_assembly_match",
                "material_specification", "critical_tolerance", "datasheet_status", "technical_validation",
            ]) for line in bop.line_ids[:500]] if bop else [],
            "mould_plans": [],
            "existing_risks": [self._plain(risk, [
                "risk_id", "source_type", "source_reference", "cause", "description", "impact_statement",
                "category", "probability", "impact", "status",
            ]) for risk in existing],
        }
        for mould in moulds:
            snapshot["mould_plans"].append({
                "header": self._plain(mould, [
                    "x_name", "x_mould_number", "x_plan_revision", "x_workflow_state", "x_lifecycle_stage",
                    "x_mould_configuration", "x_cavitation", "x_planning_confidence", "x_grouping_basis",
                    "x_planning_assumption", "x_open_technical_question", "x_customer_input_pending",
                    "x_engineering_input_pending", "x_risk_flag", "x_risk_note",
                ]),
                "parts": [self._plain(part, [
                    "x_part_number", "x_name", "x_part_category", "x_part_material", "x_surface_finish_type",
                    "x_surface_grade_code", "x_part_weight_grams", "x_qps", "x_mould_configuration",
                    "x_cavitation", "x_visual_inspection_applicability", "x_dimensional_inspection_applicability",
                    "x_missing_fields", "x_completion_percent",
                ]) for part in mould.x_part_ids[:300]],
            })
        return snapshot

    @staticmethod
    def _extract_json(text):
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(cleaned)

    def action_run_scan(self):
        self.ensure_one()
        if self.state not in ("draft", "failed"):
            raise UserError(_("Only a Ready or Failed review can be scanned."))
        parameters = self.env["ir.config_parameter"].sudo()
        api_key = os.environ.get("HJIG_CLAUDE_API_KEY") or parameters.get_param("hjig.ai.claude_api_key")
        model_name = os.environ.get("HJIG_CLAUDE_MODEL") or parameters.get_param("hjig.ai.claude_model")
        endpoint = parameters.get_param("hjig.ai.claude_endpoint", "https://api.anthropic.com/v1/messages")
        if not api_key or not model_name:
            raise UserError(_(
                "Claude Copilot is deployed but not connected. Configure HJIG_CLAUDE_API_KEY and HJIG_CLAUDE_MODEL on the Odoo server."
            ))
        snapshot = self._source_snapshot()
        source_json = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
        system_prompt = """You are Hongyi JIG's governed IG risk-analysis copilot. Analyze only the supplied project evidence. Find contradictions, missing/floating inputs, BOP and mould-interface risks, supplier/commercial readiness risks, validation gaps and schedule dependencies. Never approve a gate or claim that an unsupported fact is confirmed. Return strict JSON only with key 'risks'. Each risk must contain: source_type (sor|bop|mould_plan|design|customer|supplier|gate_review|other), source_reference, evidence_excerpt, cause, event, impact, category (technical|quality|resource|schedule|commercial|supplier|customer|other), probability (1-5 string), impact_score (1-5 string), mitigation, preventive_action, contingency, trigger, confidence (0-100 number), possible_duplicate_risk_id (string or null), and uncertainty. One row must represent one Cause -> Event -> Impact chain. Cite exact record codes/part numbers/requirement IDs where available."""
        payload = {
            "model": model_name,
            "max_tokens": 8000,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": "Review this governed project snapshot:\n" + source_json}],
        }
        try:
            response = requests.post(
                endpoint,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=payload, timeout=120,
            )
            response.raise_for_status()
            body = response.json()
            text = "\n".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")
            parsed = self._extract_json(text)
            risks = parsed.get("risks", [])
            if not isinstance(risks, list):
                raise ValueError("'risks' is not a list")
        except Exception as exc:
            self.write({"state": "failed", "failure_message": str(exc)[:2000]})
            raise UserError(_("Claude risk scan failed: %s") % str(exc)[:500]) from exc

        self.suggestion_ids.unlink()
        values = []
        allowed_categories = dict(RISK_CATEGORIES)
        for item in risks[:100]:
            probability = str(item.get("probability", "3"))
            impact = str(item.get("impact_score", "3"))
            values.append({
                "scan_id": self.id,
                "source_type": item.get("source_type") if item.get("source_type") in dict(self.env["hjig.project.risk"]._fields["source_type"].selection) else "other",
                "source_reference": item.get("source_reference") or "AI review of current project snapshot",
                "evidence_excerpt": item.get("evidence_excerpt"),
                "cause": item.get("cause") or "Unverified source gap",
                "description": item.get("event") or "Potential project risk requires employee review",
                "impact_statement": item.get("impact") or "Impact requires employee assessment",
                "category": item.get("category") if item.get("category") in allowed_categories else "other",
                "probability": probability if probability in dict(SCORE_SELECTION) else "3",
                "impact": impact if impact in dict(SCORE_SELECTION) else "3",
                "mitigation_plan": item.get("mitigation") or "Define mitigation during employee review",
                "preventive_action": item.get("preventive_action"),
                "contingency_plan": item.get("contingency"),
                "trigger_indicator": item.get("trigger"),
                "confidence": max(0, min(100, float(item.get("confidence", 0) or 0))),
                "uncertainty": item.get("uncertainty"),
                "possible_duplicate_risk_id": item.get("possible_duplicate_risk_id"),
            })
        self.env["hjig.risk.ai.suggestion"].create(values)
        self.write({
            "state": "review", "source_snapshot_hash": digest,
            "source_snapshot_summary": "SOR=%s; BOP=%s; Mould plans=%s; Existing risks=%s" % (
                snapshot["sor"] and snapshot["sor"].get("code") or "none",
                snapshot["bop"] and snapshot["bop"].get("code") or "none",
                len(snapshot["mould_plans"]), len(snapshot["existing_risks"]),
            ),
            "model_identity": model_name, "run_date": fields.Datetime.now(), "run_by_id": self.env.user.id,
            "failure_message": False,
        })
        self.env["hjig.ai.assistance.log"]._log_assistance({
            "project_id": self.project_id.id, "target_ref": "%s,%s" % (self._name, self.id),
            "capability": "validate", "model_identity": model_name,
            "permission_scope": "Latest project SOR, BOP, mould plans and existing Risk Register; no approval authority.",
            "output_summary": "%s candidate risks generated for mandatory employee review." % len(values),
            "confidence": (sum(value["confidence"] for value in values) / len(values)) if values else 0,
            "warnings": "AI output is advisory. Employee review and controlled Risk Register workflow remain mandatory.",
        })
        return True

    def action_complete_review(self):
        self.ensure_one()
        if self.state != "review":
            raise UserError(_("Only an Employee Review can be completed."))
        if self.pending_count:
            raise ValidationError(_("Review every AI suggestion before completing this review."))
        if not self.employee_additional_risks_confirmed:
            raise ValidationError(_("Confirm that additional human-identified risks were considered."))
        self.write({"state": "complete", "reviewed_by_id": self.env.user.id, "reviewed_date": fields.Datetime.now()})

    def write(self, vals):
        if self.filtered(lambda scan: scan.state == "complete") and set(vals) - {"message_follower_ids", "message_ids", "activity_ids"}:
            raise ValidationError(_("A completed AI Risk Review is read-only."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda scan: scan.state != "draft"):
            raise UserError(_("A scanned AI Risk Review cannot be deleted."))
        return super().unlink()


class HjigRiskAiSuggestion(models.Model):
    _name = "hjig.risk.ai.suggestion"
    _description = "AI Draft Risk Suggestion"
    _order = "risk_score desc, confidence desc, id"
    _rec_name = "description"

    scan_id = fields.Many2one("hjig.risk.ai.scan", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="scan_id.project_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="scan_id.company_id", store=True, readonly=True, index=True)
    source_type = fields.Selection(selection=lambda self: self.env["hjig.project.risk"]._fields["source_type"].selection, required=True)
    source_reference = fields.Char(required=True)
    evidence_excerpt = fields.Text(readonly=True)
    cause = fields.Text(required=True)
    description = fields.Text(string="Risk Event", required=True)
    impact_statement = fields.Text(required=True)
    category = fields.Selection(RISK_CATEGORIES, required=True)
    probability = fields.Selection(SCORE_SELECTION, required=True)
    impact = fields.Selection(SCORE_SELECTION, required=True)
    risk_score = fields.Integer(compute="_compute_risk_score", store=True)
    mitigation_plan = fields.Text(required=True)
    preventive_action = fields.Text()
    contingency_plan = fields.Text()
    trigger_indicator = fields.Text()
    confidence = fields.Float(readonly=True)
    uncertainty = fields.Text(readonly=True)
    possible_duplicate_risk_id = fields.Char(readonly=True)
    disposition = fields.Selection(
        [("pending", "Needs Review"), ("applied", "Added to Register"), ("merged", "Duplicate / Merged"), ("rejected", "Rejected")],
        default="pending", required=True, readonly=True, index=True,
    )
    disposition_note = fields.Text()
    risk_id = fields.Many2one("hjig.project.risk", readonly=True, copy=False, ondelete="restrict")
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)

    @api.depends("probability", "impact")
    def _compute_risk_score(self):
        for suggestion in self:
            suggestion.risk_score = int(suggestion.probability or 0) * int(suggestion.impact or 0)

    def _review_values(self, disposition):
        return {"disposition": disposition, "reviewed_by_id": self.env.user.id, "reviewed_date": fields.Datetime.now()}

    def action_add_to_register(self):
        for suggestion in self:
            if suggestion.disposition != "pending":
                raise UserError(_("This AI suggestion has already been reviewed."))
            today = fields.Date.context_today(suggestion)
            risk = self.env["hjig.project.risk"].with_context(
                hjig_programme_artifact_requirement_id=suggestion.scan_id.origin_requirement_id.id,
            ).create({
                "project_id": suggestion.project_id.id, "source_type": suggestion.source_type,
                "source_reference": suggestion.source_reference, "cause": suggestion.cause,
                "description": suggestion.description, "impact_statement": suggestion.impact_statement,
                "category": suggestion.category, "probability": suggestion.probability, "impact": suggestion.impact,
                "mitigation_plan": suggestion.mitigation_plan, "preventive_action": suggestion.preventive_action,
                "contingency_plan": suggestion.contingency_plan or "Employee to define before mitigation starts",
                "trigger_indicator": suggestion.trigger_indicator or "Employee to define before mitigation starts",
                "residual_probability": suggestion.probability, "residual_impact": suggestion.impact,
                "target_date": today + relativedelta(days=7), "next_review_date": today + relativedelta(days=2),
            })
            suggestion.write(dict(suggestion._review_values("applied"), risk_id=risk.id))
        return True

    def action_mark_duplicate(self):
        for suggestion in self:
            if suggestion.disposition != "pending":
                raise UserError(_("This AI suggestion has already been reviewed."))
            if not suggestion.disposition_note:
                raise ValidationError(_("Identify the existing Risk ID or explain the merge in Disposition Note."))
            suggestion.write(suggestion._review_values("merged"))

    def action_reject(self):
        for suggestion in self:
            if suggestion.disposition != "pending":
                raise UserError(_("This AI suggestion has already been reviewed."))
            if not suggestion.disposition_note:
                raise ValidationError(_("A rejection reason is required."))
            suggestion.write(suggestion._review_values("rejected"))

    def unlink(self):
        if self.filtered(lambda item: item.scan_id.state != "draft"):
            raise UserError(_("AI suggestions are auditable and cannot be deleted after scanning."))
        return super().unlink()
