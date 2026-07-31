import base64
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RiskCalculatorController(http.Controller):

    @http.route('/api/risk/submit', type='json',
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
                'partner_name': data.get('company', ''),
                'contact_name': data.get('name', ''),
                'email_from': data.get('email', ''),
                'mobile': data.get('whatsapp', ''),
                'stage_id': pre_fd.id,
                'tag_ids': [(4, tag.id)],
                'priority': '1',

                # Business stake
                'x_price_per_unit': float(data.get('price_per_unit', 0) or 0),
                'x_year1_units': int(data.get('year1_units', 0) or 0),
                'x_year2_units': int(data.get('year2_units', 0) or 0),
                'x_year3_units': int(data.get('year3_units', 0) or 0),
                'x_market_life': data.get('market_life', ''),
                'x_business_at_stake': data.get('business_at_stake', ''),

                # Project context
                'x_project_type': data.get('q1', ''),
                'x_industry': data.get('q2', ''),
                'x_visitor_role': data.get('visitor_role', '') or data.get('q3', ''),
                'description': 'Role: {}'.format(data.get('role', '')),

                # Governance questions
                'x_design_team': data.get('q7', ''),
                'x_design_check': data.get('q8', ''),
                'x_toolmaker_selection': data.get('q9', ''),
                'x_quality_ownership': data.get('q10', ''),
                'x_programme_owner': data.get('q11', ''),

                # Delivery risk
                'x_launch_deadline': data.get('q12', ''),
                'x_delay_impact': data.get('q13', ''),
                'x_mould_count': data.get('q14', ''),
                'x_trial_budget': data.get('q15', ''),
                'x_quality_standard': data.get('q16', ''),

                # Risk zones — lowercase to match Selection field values
                'x_risk_design': rl(data.get('design_risk')),
                'x_risk_cost': rl(data.get('cost_risk')),
                'x_risk_supplier': rl(data.get('supplier_risk')),
                'x_risk_quality': rl(data.get('quality_risk')),
                'x_risk_delivery': rl(data.get('delivery_risk')),

                # Summary
                'x_high_risk_zones': int(data.get('high_risk_zones', 0) or 0),
                'x_wants_discussion': data.get('wants_discussion', '') == 'Yes',
            })

            _logger.info('Risk Calculator lead created: %s', lead.id)
            attachment = self._attach_risk_report(lead)
            self._send_risk_report_email(lead, attachment)
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

    def _attach_risk_report(self, lead):
        """Render the Risk Exposure qweb report and attach it as a PDF
        on the crm.lead record. Failure here must never break lead creation."""
        try:
            report = request.env.ref(
                'new_hongyijig_custom.report_risk_exposure')
            pdf_content, _report_type = report.sudo()._render_qweb_pdf(
                report.id, [lead.id])

            attachment = request.env['ir.attachment'].sudo().create({
                'name': 'Risk Exposure Report - %s.pdf' % (lead.name or lead.id),
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'crm.lead',
                'res_id': lead.id,
                'mimetype': 'application/pdf',
            })
            _logger.info(
                'Risk Exposure report attached to lead %s', lead.id)
            return attachment
        except Exception as e:
            _logger.error(
                'Failed to attach Risk Exposure report to lead %s: %s',
                lead.id, str(e))
            return False

    def _send_risk_report_email(self, lead, attachment):
        """Render the mail template, log it in the chatter, and send the
        email with the risk report attached. Never break lead creation."""
        try:
            if not attachment:
                _logger.warning(
                    'No attachment available, skipping email for lead %s', lead.id)
                return
            if not lead.email_from:
                _logger.warning(
                    'No recipient email for lead %s', lead.id)
                return

            template = request.env.ref(
                'new_hongyijig_custom.mail_template_risk_exposure_report').sudo()

            # ── Render subject & body from the XML template ────────────
            rendered_subject = template._render_field(
                'subject', [lead.id])[lead.id]
            rendered_body = template._render_field(
                'body_html', [lead.id])[lead.id]

            # ── 1. Log note in chatter (always visible) ────────────────
            lead.sudo().message_post(
                body='Risk report emailed to %s (cc: intake@hongyijig.com)' % lead.email_from,
                subject=rendered_subject,
                attachment_ids=[attachment.id],
            )

            # ── 2. Actually send the email ──────────────────────────────
            mail_values = {
                'subject': rendered_subject,
                'email_from': 'jagdipkhattar@hongyijig.com',
                'email_to': lead.email_from,
                'email_cc': 'intake@hongyijig.com',
                'body_html': rendered_body,
                'attachment_ids': [(4, attachment.id)],
                'auto_delete': False,
                'model': 'crm.lead',
                'res_id': lead.id,
            }
            mail = request.env['mail.mail'].sudo().create(mail_values)
            mail.sudo().send(auto_commit=True)

            if mail.state == 'exception':
                _logger.error(
                    'Mail send failed for lead %s: %s', lead.id, mail.failure_reason)
            else:
                _logger.info(
                    'Risk report email sent to %s for lead %s (state=%s)',
                    lead.email_from, lead.id, mail.state)

        except Exception:
            _logger.exception(
                'Failed to send risk report email for lead %s', lead.id)