from odoo import models, fields


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
