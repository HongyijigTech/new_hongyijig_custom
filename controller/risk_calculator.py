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

    # def _send_risk_report_email(self, lead, attachment):
    #     """Email the Risk Exposure report to the lead's email_from, CC intake@hongyijig.com."""
    #     try:
    #         if not attachment:
    #             _logger.warning(
    #                 'No attachment available, skipping email for lead %s', lead.id)
    #             return
    #         if not lead.email_from:
    #             _logger.warning(
    #                 'No email_from set, skipping email for lead %s', lead.id)
    #             return
    #
    #         mail_values = {
    #             'subject': 'Your Risk Exposure Report - %s' % (lead.partner_name or lead.name),
    #             'email_from': 'jagdipkhattar@hongyijig.com',
    #             'email_to': lead.email_from,
    #             'email_cc': 'intake@hongyijig.com',
    #             'body_html': """
    #                 <p>Dear %s,</p>
    #                 <p>Thank you for using our Risk Calculator. Please find your
    #                 Risk Exposure Report attached.</p>
    #                 <p>Our team will be in touch shortly to discuss the results.</p>
    #             """ % (lead.contact_name or 'Sir/Madam'),
    #             'attachment_ids': [(4, attachment.id)],
    #             'auto_delete': False,
    #         }
    #         mail = request.env['mail.mail'].sudo().create(mail_values)
    #         mail.sudo().send(auto_commit=True)
    #         _logger.info(
    #             'Risk report email sent to %s (cc intake@hongyijig.com) for lead %s',
    #             lead.email_from, lead.id)
    #     except Exception as e:
    #         _logger.error(
    #             'Failed to send risk report email for lead %s: %s',
    #             lead.id, str(e))

    def _send_risk_report_email(self, lead, attachment):
        """Email the Risk Exposure report to the lead."""

        try:
            if not attachment:
                _logger.warning(
                    "No attachment available, skipping email for lead %s", lead.id
                )
                return

            if not lead.email_from:
                _logger.warning(
                    "No recipient email available for lead %s", lead.id
                )
                return

            # ----------------------------------------------------------
            # Dynamic Observation
            # ----------------------------------------------------------

            if lead.x_high_risk_zones >= 3:
                observation = f"""
                <p style="font-size:14px;color:#1A1A1A;line-height:1.8;margin:0 0 16px 0;">
                    I have looked at your inputs.
                    <strong>{lead.x_high_risk_zones} of your 5 governance zones are rated HIGH</strong>
                    - with
                    <strong>{lead.x_business_at_stake or 'significant business value'}</strong>
                    depending on this programme going right.
                </p>
                """

            elif lead.x_high_risk_zones == 2:
                observation = f"""
                <p style="font-size:14px;color:#1A1A1A;line-height:1.8;margin:0 0 16px 0;">
                    I have looked at your inputs.
                    <strong>2 of your 5 governance zones are rated HIGH</strong>
                    - with
                    <strong>{lead.x_business_at_stake or 'significant business value'}</strong>
                    depending on this programme going right.
                </p>
                """

            elif lead.x_high_risk_zones == 1:
                observation = """
                <p style="font-size:14px;color:#1A1A1A;line-height:1.8;margin:0 0 16px 0;">
                    I have looked at your inputs.
                    <strong>1 of your 5 governance zones is rated HIGH.</strong>
                    The report details what this means before execution begins.
                </p>
                """

            else:
                observation = """
                <p style="font-size:14px;color:#1A1A1A;line-height:1.8;margin:0 0 16px 0;">
                    I have looked at your inputs.
                    Your programme is in a strong governance position across all 5
                    governance zones. The report details how to protect this as
                    execution begins.
                </p>
                """

            # ----------------------------------------------------------
            # Consequence
            # ----------------------------------------------------------

            consequence = ""

            if lead.x_high_risk_zones >= 1:
                consequence = """
                <p style="font-size:14px;color:#1A1A1A;line-height:1.8;margin:0 0 16px 0;">
                    The gaps are still closable. But not after tooling begins.
                </p>
                """

            # ----------------------------------------------------------
            # HTML Body
            # ----------------------------------------------------------

            body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    </head>

    <body style="margin:0;padding:0;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#1A1A1A;">

    <table width="100%" cellpadding="0" cellspacing="0" style="padding:36px 0;background:#ffffff;">
    <tr>
    <td align="center">

    <table width="520" cellpadding="0" cellspacing="0" style="width:100%;max-width:520px;">

    <tr>
    <td>

    <p style="font-size:14px;line-height:1.7;">
    Dear {lead.contact_name or lead.partner_name or 'there'} Ji,
    </p>

    <p style="font-size:14px;line-height:1.8;">
    Your report is attached.
    </p>

    {observation}

    {consequence}

    <p style="font-size:14px;line-height:1.8;">
    If you want to talk through what this means specifically for your programme –
    20 minutes, no pitch – reach me directly.
    </p>

    <p style="font-size:15px;font-weight:bold;">
    +91 88839 12346
    </p>

    <hr style="border:none;border-top:1px solid #EBEBEB;">

    <table cellpadding="0" cellspacing="0">
    <tr>

    <td style="padding-right:15px;">
    <img src="https://www.hongyijig.com/media/8dfc8d2b-jagdip-khattar.jpg"
    width="52"
    height="52"
    style="border-radius:50%;display:block;">
    </td>

    <td>

    <p style="margin:0;font-size:14px;font-weight:bold;">
    Jagdip Khattar
    </p>

    <p style="margin:2px 0;font-size:12px;">
    Founder, Hongyi JIG Rapid Technologies
    </p>

    <p style="margin:2px 0;font-size:12px;">
    <a href="https://www.hongyijig.com">
    www.hongyijig.com
    </a>
    </p>

    </td>

    </tr>
    </table>

    <p style="font-size:10px;color:#999999;margin-top:25px;">
    If the PDF report is not in your inbox, please check your spam folder.<br/>
    Subject line: <strong>Your Risk Report - Hongyi JIG</strong>
    </p>

    </td>
    </tr>
    </table>

    </td>
    </tr>
    </table>

    </body>
    </html>
    """

            body = (
                "Your Risk Exposure Report is attached.\n\n"
                "If you have any questions, please contact us.\n\n"
                "Hongyi JIG Rapid Technologies")
            mail_values = {
                'subject': 'Your Risk Exposure Report - %s' % (lead.partner_name or lead.name),
                'email_from': 'jagdipkhattar@hongyijig.com',
                'email_to': lead.email_from,
                'email_cc': 'intake@hongyijig.com',
                'body': body,
                'body_html': body_html,
                'attachment_ids': [(4, attachment.id)],
                'auto_delete': False}

            mail = request.env["mail.mail"].sudo().create(mail_values)
            mail.sudo().send(auto_commit=True)
            _logger.info(
                "Risk report email sent to %s for lead %s",
                lead.email_from, lead.id, )
        except Exception:
            _logger.exception(
                "Failed to send risk report email for lead %s",
                lead.id, )
