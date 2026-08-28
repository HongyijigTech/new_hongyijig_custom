# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'HongyiJigTechNew',
    'version': '1.18',
    'summary': 'Hongyijig Tech New',
    'sequence': 10,
    'description': """
Hongyijig Tech
====================
    """,
    'category': 'Hongyijig Custom New',
    'website': 'https://www.hongyijig.com/',
    'depends': ['base', 'mail', 'crm', 'contacts', 'sale_crm', 'project'],
    'data': ['security/security.xml',
             'security/ir.model.access.csv',
             'data/project_document_sequence.xml',
             'data/governance_master_data.xml',
             'data/programme_template_data.xml',
             'data/engineering_reference_data.xml',
             'data/hjig.inspection.checkpoint.master.csv',
             'data/native_form_sequence.xml',
             'data/native_form_template_data.xml',
             'views/crm_lead.xml',
             'views/risk_Report_temp.xml',
             'views/email_template.xml',
             'views/project_document_views.xml',
             'views/governance_master_views.xml',
             'views/programme_template_views.xml',
             'views/native_form_views.xml',
             'views/project_register_views.xml',
             'views/engineering_reference_views.xml'],
    'installable': True,
    'application': True,
    'assets': {},
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
