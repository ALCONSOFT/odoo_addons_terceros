# -*- coding: utf-8 -*-
{
    'name': "Bank Deposit Management",

    'summary': """
        Managing customer deposits and withdrawals""",

    'description': """
        Managing customer deposits and withdrawals
    """,

    'author': "Patrick Isaiah",
    'website': "http://www.patrickisaiah.com",

    'category': 'Uncategorized',
    'version': '0.1',
    'application': True,
    'images': ['static/description/banner.png'],
    'depends': ['base', 'web', 'mail'],
    'license': 'OPL-1',

    'data': [
        'security/ir.model.access.csv',
        'security/group_security_view.xml',
        'data/ir_sequence_data.xml',
        'data/mail_template.xml',
        'views/bank_view.xml',
        'views/transaction_view.xml',
        'views/customer_view.xml',
        'views/user_view.xml',
        'views/templates.xml',
        'views/menus.xml',
        'report/transaction_receipt.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
}
