# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'HongyiJigTechNew',
    'version': '1.6',
    'summary': 'Hongyijig Tech New',
    'sequence': 10,
    'description': """
Hongyijig Tech
====================
    """,
    'category': 'Hongyijig Custom New',
    'website': 'https://www.hongyijig.com/',
    'depends': ['base', 'crm', 'contacts', 'sale_crm', 'project'],
    'data': ['security/security.xml',
             'security/ir.model.access.csv',
             'data/project_document_sequence.xml',
             'data/foundation_sequence.xml',
             'data/governance_master_data.xml',
             'views/crm_lead.xml',
             'views/risk_Report_temp.xml',
             'views/email_template.xml',
             'views/project_document_views.xml',
             'views/foundation_views.xml',
             'views/governance_master_views.xml'],
    'installable': True,
    'application': True,
    'assets': {},
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
