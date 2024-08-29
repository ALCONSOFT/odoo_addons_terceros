# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': "Account Payment Dynamic Approval | Accounting Payment Multi Level Approval",
    'version': '16.0.0.1',
    'category': 'Accounting',
    'summary': "Accounting Payment Dynamic Approval on payment double approval payment triple approval payment user approval Account dynamic approval dynamic payment approval payment multi approval Account payment multi level approval payment multiple approval payment",
    'description': """

        Payment Dynamic Approval Odoo App helps users to dynamic and multi level approvals in payment. User can configure dynamic approval from invoicing configuration and set approval based on minimum amount. Payment should be approved by user and specific group. User can view email notification about approval and rejection of payment.
    
    """,
    'author': 'BrowseInfo',
    "price": 25,
    "currency": 'EUR',
    'website': 'https://www.browseinfo.com',
    'depends': ['base' ,'account'],
    'data': [
         'security/ir.model.access.csv',
         'security/payment_approval_security.xml',
         'views/account_payment_view.xml',
         'views/account_payment_approval.xml',
         'views/approval_menu.xml',
         'data/payment_mail_template.xml',
         'data/payment_reject_mail_template.xml',
         'data/payment_confirm_mail_template.xml',
         'wizard/group_wizard_view.xml',
    ],
    'license':'OPL-1',
    'installable': True,
    'auto_install': False,
    'live_test_url':'https://youtu.be/c54by6Mrqz4',
    "images":['static/description/Account-Payment-Dynamic-Approval-Banner.gif'],
}
