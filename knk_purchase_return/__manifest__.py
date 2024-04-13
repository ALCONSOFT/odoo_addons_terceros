# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).
{
    'name': 'Purchase Return',
    'version': '16.0.1.0',
    "summary": 'Purchase Return Module allows user to efficiently track and manage purchase order along with their delivery returns, user can return products from purchase order itself without interacting with stock picking.  | Purchase Return | Return Order | Purchase Picking | In Picking | Return Picking | Return Purchase Order |',
    'description': """
Purchase Return
====================
Using this Module user can return Purchase order directly from purchase and stocks are managed automatically.
==> Features
    -> Return products from purchase order directly.
    -> Stock gets updated automatically.
    -> Picks gets created automatically.
    -> Track previous returns from return history.
    -> Can Return Multiple products at a time from current purchase order.
    """,
    'category': 'Inventory/Purchase',
    'author': 'Kanak Infosystems LLP.',
    'website': 'https://www.kanakinfosystems.com',
    'license': 'OPL-1',
    'images': ['static/description/banner.jpg'],
    'depends': ['stock', 'purchase','utm'],
    'data': [
        'security/ir.model.access.csv',
        'data/return_sequence_data.xml',
        'wizard/knk_purchase_return_wizard_views.xml',
        'views/purchase_order_return_views.xml',
        'views/purchase_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'currency': 'EUR',
    'price': '30',
}
