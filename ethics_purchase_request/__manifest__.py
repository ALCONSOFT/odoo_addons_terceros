# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Purchase Request',
    'version': '16.0.0.1',
    'sequence': 10,
    'summary': """
        Create Purchase Request And Purchase RFQ""",

    'description': """
        Purchase request create vendor wise new purchase rfq.
        if vendor is not set on purchase request line
        than it will create new purchase request.

    """,
    'author': "Ethics Infotech LLP",
    'website': "http://www.ethicsinfotech.in",
    'depends': ['web', 'purchase', 'hr'],
    'license': 'OPL-1',
    'price': 20,
    'currency': 'USD',
    'support': 'info@ethicsinfotech.in',
    'images': ['static/description/banner.gif'],
    'data': [
        'data/purchase_request_data.xml',
        'security/security_view.xml',
        'security/ir.model.access.csv',
        'view/purchase_order_view.xml',
        'view/purchase_request_view.xml',
        'view/pr_reject_reason_view.xml',
        'wizard/back_purchase_request_view.xml',
        'wizard/add_pr_reject_reason_view.xml'
    ],
    'assets': {
        'web.assets_backend': [
            'ethics_purchase_request/static/src/js/form_renderer.js',
        ],
    },
    'installable': True
}
