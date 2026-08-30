from odoo import _, api, fields, models
from odoo.exceptions import UserError


ACCOUNTABILITY_EMAILS = {
    "pre_fd_fd": "intake@thehongyijig.com",
    "p_s": "businesscrm@thehongyijig.com",
}

CRM_SPINE_STAGE_XMLIDS = {
    "pre_fd": "new_hongyijig_custom.crm_stage_hjig_pre_fd",
    "fd": "new_hongyijig_custom.crm_stage_hjig_fd_series",
    "p": "new_hongyijig_custom.crm_stage_hjig_p_series",
    "s": "new_hongyijig_custom.crm_stage_hjig_s_series",
    "order_punch": "new_hongyijig_custom.crm_stage_hjig_order_punch",
    "b_handover": "new_hongyijig_custom.crm_stage_hjig_bseries_handover",
}

STAGE_ACCOUNTABILITY = {
    "pre_fd": "pre_fd_fd",
    "fd": "pre_fd_fd",
    "p": "p_s",
    "s": "p_s",
    "order_punch": "p_s",
    "b_handover": "p_s",
}


class CrmLeadRiskFields(models.Model):
    _inherit = 'crm.lead'

    # ─── Business stake ───────────────────────────────────────────────
    mobile = fields.Char(string='Mobile')
    brief_project_context = fields.Char(string='Brief Project Context')
    biggest_current_risk = fields.Char(string='Biggest Current Risk')
    preferred_contact_method = fields.Selection([('email', 'Email'), ('phone', 'Phone Call'), ('whatsapp', 'WhatsApp'), ], string='Preferred Contact Method')
    x_price_per_unit    = fields.Float(  string='Price Per Unit (Risk Calc)')
    x_year1_units       = fields.Integer(string='Year 1 Units (Risk Calc)')
    x_year2_units       = fields.Integer(string='Year 2 Units (Risk Calc)')
    x_year3_units       = fields.Integer(string='Year 3 Units (Risk Calc)')
    x_market_life       = fields.Char(   string='Market Life (Risk Calc)')
    x_business_at_stake = fields.Char(   string='Business at Stake (Risk Calc)')

    # ─── Project context (Q1-Q3) ──────────────────────────────────────
    x_project_type      = fields.Char(string='Project Type (Q1)')
    x_industry      = fields.Char(string='Industry (Q2)')
    x_visitor_role      = fields.Char(string='Visitor Role (Q3)')

    # ─── Governance questions (Q7-Q11) ───────────────────────────────
    x_design_team           = fields.Char(string='Design Team (Q7)')
    x_design_check          = fields.Char(string='Independent Design Check (Q8)')
    x_toolmaker_selection   = fields.Char(string='Toolmaker Selection (Q9)')
    x_quality_ownership     = fields.Char(string='Quality Issue Ownership (Q10)')
    x_programme_owner       = fields.Char(string='Programme Owner (Q11)')

    # ─── Delivery risk (Q12-Q16) ─────────────────────────────────────
    x_launch_deadline   = fields.Char(string='Launch Deadline (Q12)')
    x_delay_impact      = fields.Char(string='Business Impact of Delay (Q13)')
    x_mould_count       = fields.Char(string='Number of Moulds (Q14)')
    x_trial_budget      = fields.Char(string='Trial/Rework Budget (Q15)')
    x_quality_standard  = fields.Char(string='Quality Standard (Q16)')

    # ─── Computed risk zones ─────────────────────────────────────────
    x_risk_design   = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Design Risk')
    x_risk_cost     = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Cost Risk')
    x_risk_supplier = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Supplier Risk')
    x_risk_quality  = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Quality Risk')
    x_risk_delivery = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Delivery Risk')

    x_high_risk_zones   = fields.Integer(string='High Risk Zone Count')
    x_wants_discussion  = fields.Boolean(string='Wants 20-min Discussion')


class CrmLeadHongyiRevenueSpine(models.Model):
    """Keep the complete Pre-FD to B0 commercial journey on one CRM opportunity."""

    _inherit = "crm.lead"

    hjig_sseries_case_ids = fields.One2many(
        "hjig.sseries.case", "lead_id", string="S-Series Projects", readonly=True
    )
    hjig_sseries_case_count = fields.Integer(
        compute="_compute_hjig_sseries_summary", string="S-Series Projects"
    )
    hjig_sseries_current_status = fields.Selection(
        [
            ("s0_received", "Submission Record"),
            ("s1_review", "Internal Review"),
            ("s2_assessment", "Governance Assessment"),
            ("s3_proposal", "Commercial Proposal"),
            ("s4_activation", "Activation Pack"),
            ("s5_sourcing", "Sourcing Pack"),
            ("s6_handover", "Team Handover"),
            ("b0_released", "B-Series Handover Released"),
            ("cancelled", "Cancelled"),
        ],
        compute="_compute_hjig_sseries_summary",
        string="S-Series Status",
    )
    hjig_sseries_next_action = fields.Char(
        compute="_compute_hjig_sseries_summary", string="Next S-Series Action"
    )
    hjig_sseries_blocker_count = fields.Integer(
        compute="_compute_hjig_sseries_summary", string="Blocked Projects"
    )
    hjig_sseries_can_start = fields.Boolean(compute="_compute_hjig_sseries_summary")
    hjig_accountability_phase = fields.Selection(
        [
            ("pre_fd_fd", "Pre-FD / FD"),
            ("p_s", "P-Series / S-Series / Order Punch"),
        ],
        readonly=True,
        tracking=True,
        copy=False,
    )
    hjig_accountable_email = fields.Char(readonly=True, tracking=True, copy=False)
    hjig_owner_routing_state = fields.Selection(
        [("assigned", "Assigned"), ("missing", "Owner Account Missing")],
        readonly=True,
        tracking=True,
        copy=False,
    )
    hjig_owner_routing_note = fields.Char(readonly=True, tracking=True, copy=False)

    @api.depends(
        "hjig_sseries_case_ids.stage",
        "hjig_sseries_case_ids.next_action",
        "hjig_sseries_case_ids.exception_state",
    )
    def _compute_hjig_sseries_summary(self):
        stage_rank = {
            "s0_received": 0,
            "s1_review": 1,
            "s2_assessment": 2,
            "s3_proposal": 3,
            "s4_activation": 4,
            "s5_sourcing": 5,
            "s6_handover": 6,
            "b0_released": 7,
            "cancelled": 8,
        }
        for lead in self:
            cases = lead.hjig_sseries_case_ids.sorted(
                lambda case: (stage_rank.get(case.stage, 99), case.id)
            )
            active_cases = cases.filtered(lambda case: case.stage != "cancelled")
            controlling_case = active_cases[:1] or cases[:1]
            lead.hjig_sseries_case_count = len(cases)
            lead.hjig_sseries_current_status = controlling_case.stage if controlling_case else False
            lead.hjig_sseries_next_action = controlling_case.next_action if controlling_case else False
            lead.hjig_sseries_blocker_count = len(
                active_cases.filtered(lambda case: case.exception_state == "blocked")
            )
            lead.hjig_sseries_can_start = bool(
                active_cases and all(case.stage == "s0_received" for case in active_cases)
            )

    @api.model
    def _hjig_stage(self, key):
        xmlid = CRM_SPINE_STAGE_XMLIDS[key]
        stage = self.env.ref(xmlid, raise_if_not_found=False)
        if not stage:
            raise UserError(_("The governed CRM stage %s is not configured.") % key)
        return stage

    @api.model
    def _hjig_stage_key_from_id(self, stage_id):
        for key, xmlid in CRM_SPINE_STAGE_XMLIDS.items():
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage and stage.id == stage_id:
                return key
        return False

    @api.model
    def _hjig_accountability_values(self, phase):
        if phase not in ACCOUNTABILITY_EMAILS:
            raise UserError(_("Unsupported CRM accountability phase: %s") % phase)
        parameter_key = "hjig.crm.%s_owner_email" % phase
        email = self.env["ir.config_parameter"].sudo().get_param(
            parameter_key, ACCOUNTABILITY_EMAILS[phase]
        ).strip().lower()
        owner = self.env["res.users"].sudo().search([
            ("active", "=", True),
            ("share", "=", False),
            "|",
            ("login", "=ilike", email),
            ("partner_id.email", "=ilike", email),
        ], limit=1)
        values = {
            "hjig_accountability_phase": phase,
            "hjig_accountable_email": email,
            "hjig_owner_routing_state": "assigned" if owner else "missing",
            "hjig_owner_routing_note": (
                False if owner else _("Create or activate the internal Odoo user %s.") % email
            ),
            "user_id": owner.id if owner else False,
        }
        return values

    def _hjig_route_accountability(self, phase):
        values = self._hjig_accountability_values(phase)
        return self.with_context(hjig_skip_accountability_sync=True).sudo().write(values)

    def _hjig_move_on_spine(self, stage_key):
        stage = self._hjig_stage(stage_key)
        phase = STAGE_ACCOUNTABILITY[stage_key]
        values = {"stage_id": stage.id, **self._hjig_accountability_values(phase)}
        return self.with_context(hjig_skip_accountability_sync=True).sudo().write(values)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            stage_id = values.get("stage_id")
            if stage_id and not values.get("hjig_accountability_phase"):
                stage_key = self._hjig_stage_key_from_id(stage_id)
                if stage_key:
                    routing = self._hjig_accountability_values(STAGE_ACCOUNTABILITY[stage_key])
                    for field_name, value in routing.items():
                        values.setdefault(field_name, value)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("stage_id") and not self.env.context.get("hjig_skip_accountability_sync"):
            stage_key = self._hjig_stage_key_from_id(vals["stage_id"])
            if stage_key:
                vals = dict(vals, **self._hjig_accountability_values(STAGE_ACCOUNTABILITY[stage_key]))
        return super().write(vals)

    def action_hjig_retry_owner_routing(self):
        for lead in self:
            phase = lead.hjig_accountability_phase or "pre_fd_fd"
            lead._hjig_route_accountability(phase)
        return True

    def action_hjig_start_sseries(self):
        self.ensure_one()
        cases = self.hjig_sseries_case_ids.filtered(lambda case: case.stage == "s0_received")
        if not cases or len(cases) != len(self.hjig_sseries_case_ids.filtered(
            lambda case: case.stage != "cancelled"
        )):
            raise UserError(_("All active portfolio projects must be ready at Submission Record."))
        cases.action_start_internal_review()
        return True

    def action_open_hjig_sseries(self):
        self.ensure_one()
        cases = self.hjig_sseries_case_ids
        if not cases:
            raise UserError(_("This opportunity has no S-Series projects."))
        action = self.env["ir.actions.actions"]._for_xml_id(
            "new_hongyijig_custom.action_hjig_sseries_cases"
        )
        action["domain"] = [("lead_id", "=", self.id)]
        action["context"] = {"default_lead_id": self.id, "create": False}
        if len(cases) == 1:
            action.update({"view_mode": "form", "res_id": cases.id, "views": [(False, "form")]})
        return action
