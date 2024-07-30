# -*- coding: utf-8 -*-
# License: Odoo Proprietary License v1.0

{
    'name': 'Odoo 16 Accounting Excel Reports',
    'version': '16.0.1.0.1',
    'category': 'Invoicing Management',
    'summary': 'Accounting Excel Reports, Odoo Excel Reports, Odoo Accounting Excel Reports, Odoo Financial Reports, '
               'Accounting Reports In Excel For Odoo 16, Financial Reports in Excel, Odoo Account Reports',
    'description': 'Accounting Excel Reports, Odoo Excel Reports, Odoo Accounting Excel Reports, Odoo Financial Reports, '
               'Accounting Reports In Excel For Odoo 16, Financial Reports in Excel, Odoo Account Reports',
    'sequence': '5',
    'live_test_url': 'https://www.youtube.com/watch?v=pz83Q9dobOM',
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': "OPL-1",
    'price': 30.00,
    'currency': 'USD',
    'website': '',
    'depends': ['accounting_pdf_reports'],
    'images': ['static/description/banner.gif'],
    'demo': [],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_excel_reports.xml',
        'views/settings.xml',
        'report/report.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {
        "web.assets_backend": [
            "accounting_excel_reports/static/src/js/action_manager_report.esm.js",
        ],
    },
}
