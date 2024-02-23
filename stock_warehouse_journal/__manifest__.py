# -*- coding: utf-8 -*-

{
    'name': 'Stock Warehouse Journal',
    'summary': 'Stock Warehouse Journal',
    'version': '16.0.2.0',
    'category': 'Warehouse',
    'website': 'www.openvalue.cloud',
    'author': "OpenValue",
    'support': 'info@openvalue.cloud',
    'license': "Other proprietary",
    'price': 0.00,
    'currency': 'EUR',
    'depends': [
        'stock',
        ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/stock_warehouse_journal.xml',
        'reports/stock_warehouse_journal_report.xml',
        ],
    'application': False,
    'installable': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
