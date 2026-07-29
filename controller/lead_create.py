import json
import logging
from odoo import http
from odoo.http import request
_logger = logging.getLogger(__name__)

class WebsiteLeadController(http.Controller):
    @http.route('/api/create_lead', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def create_lead(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
        except (ValueError, TypeError):
            return request.make_json_response(
                {'success': False, 'error': 'Invalid JSON payload'}, status=400)
        if 'params' in data:
            data = data['params']
        required = ['name', 'company', 'title', 'email']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return request.make_json_response(
                {'success': False, 'error': f'Missing fields: {", ".join(missing)}'},status=400)
        contact_map = {'Email': 'email','Phone call': 'phone','WhatsApp': 'whatsapp',}
        preferred_contact = contact_map.get(data.get('preferred_contact'), data.get('preferred_contact'))
        phone_number = data.get('phone_number') or data.get('phone')
        try:
            lead_vals = {
                'contact_name': data.get('name'),
                'name': data.get('company') or 'Website Lead',
                'function': data.get('title'),
                'email_from': data.get('email'),
                'preferred_contact_method': preferred_contact,
                'brief_project_context': data.get('brief_project_context'),
                'biggest_current_risk': data.get('biggest_current_risk')}
            if preferred_contact == 'phone':
                lead_vals['phone'] = data.get('phone')
            elif preferred_contact == 'whatsapp':
                lead_vals['mobile'] = data.get('mobile') or data.get('whatsapp')
            lead = request.env['crm.lead'].sudo().create(lead_vals)
        except Exception as e:
            _logger.exception('Failed to create lead from website')
            return request.make_json_response(
                {'success': False, 'error': str(e)}, status=500)
        return request.make_json_response({'success': True, 'lead_id': lead.id})
