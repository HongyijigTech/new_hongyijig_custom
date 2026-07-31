# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'HongyiJigTechNew',
    'version': '1.4',
    'summary': 'Hongyijig Tech New',
    'sequence': 10,
    'description': """
Hongyijig Tech
====================
    """,
    'category': 'Hongyijig Custom New',
    'website': 'https://www.hongyijig.com/',
    'depends': ['base', 'crm', 'contacts','sale_crm'],
    'data': ['views/crm_lead.xml',
             'views/risk_Report_temp.xml',
             'views/email_template.xml'],
    'installable': True,
    'application': True,
    'assets': {},
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
