import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RiskCalculatorController(http.Controller):

    @http.route('/api/risk-calculator/submit', type='json',
                auth='public', methods=['POST'], csrf=False, cors='*')
    def submit_risk_calculator(self, **kwargs):
        try:
            data = request.get_json_data()

            # ── Find Pre-FD stage ──────────────────────────────────
            pre_fd = request.env['crm.stage'].sudo().search(
                [('name', 'ilike', 'Pre-FD')], limit=1)
            if not pre_fd:
                pre_fd = request.env['crm.stage'].sudo().search([], limit=1)

            # ── Find or create Risk-Calculator-Inbound tag ─────────
            tag = request.env['crm.tag'].sudo().search(
                [('name', '=', 'Risk-Calculator-Inbound')], limit=1)
            if not tag:
                tag = request.env['crm.tag'].sudo().create(
                    {'name': 'Risk-Calculator-Inbound'})

            # ── Helper: lowercase risk level ───────────────────────
            def rl(val):
                return (val or '').lower() or False

            # ── Create lead ────────────────────────────────────────
            lead = request.env['crm.lead'].sudo().create({
                # Basic fields
                'name': '[Risk Calculator] {}'.format(
                    data.get('company', 'Unknown')),
                'partner_name':  data.get('company', ''),
                'contact_name':  data.get('name', ''),
                'email_from':    data.get('email', ''),
                'mobile':        data.get('whatsapp', ''),
                'stage_id':      pre_fd.id,
                'tag_ids':       [(4, tag.id)],
                'priority':      '1',

                # Business stake
                'x_price_per_unit':    float(data.get('price_per_unit', 0) or 0),
                'x_year1_units':       int(data.get('year1_units', 0) or 0),
                'x_year2_units':       int(data.get('year2_units', 0) or 0),
                'x_year3_units':       int(data.get('year3_units', 0) or 0),
                'x_market_life':       data.get('market_life', ''),
                'x_business_at_stake': data.get('business_at_stake', ''),

                # Project context
                'x_project_type':  data.get('q1', ''),
                'x_industry':      data.get('q2', ''),
                'x_visitor_role':  data.get('visitor_role', '') or data.get('q3', ''),
                'description':     'Role: {}'.format(data.get('role', '')),

                # Governance questions
                'x_design_team':         data.get('q7', ''),
                'x_design_check':        data.get('q8', ''),
                'x_toolmaker_selection': data.get('q9', ''),
                'x_quality_ownership':   data.get('q10', ''),
                'x_programme_owner':     data.get('q11', ''),

                # Delivery risk
                'x_launch_deadline':  data.get('q12', ''),
                'x_delay_impact':     data.get('q13', ''),
                'x_mould_count':      data.get('q14', ''),
                'x_trial_budget':     data.get('q15', ''),
                'x_quality_standard': data.get('q16', ''),

                # Risk zones — lowercase to match Selection field values
                'x_risk_design':   rl(data.get('design_risk')),
                'x_risk_cost':     rl(data.get('cost_risk')),
                'x_risk_supplier': rl(data.get('supplier_risk')),
                'x_risk_quality':  rl(data.get('quality_risk')),
                'x_risk_delivery': rl(data.get('delivery_risk')),

                # Summary
                'x_high_risk_zones':  int(data.get('high_risk_zones', 0) or 0),
                'x_wants_discussion': data.get('wants_discussion', '') == 'Yes',
            })

            _logger.info('Risk Calculator lead created: %s', lead.id)

            return {
                'success': True,
                'lead_id': lead.id,
                'message': 'Lead created successfully',
            }

        except Exception as e:
            _logger.error('Risk Calculator error: %s', str(e))
            return {
                'success': False,
                'error': str(e),
            }
