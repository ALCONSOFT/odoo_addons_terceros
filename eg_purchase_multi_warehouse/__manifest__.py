{
    'name': 'Multi Warehouse in Purchase',
    'version': '16.0',
    'category': 'Purchase',
    'summery': 'Multi Warehouse in Purchase',
    'author': 'INKERP',
    'website': "https://www.inkerp.com",
    'depends': ['purchase', 'purchase_stock'],
    
    'data': [
        'views/purchase_order_view.xml',
        'views/purchase_order_report.xml',
    ],
    
    'images': ['static/description/banner.png'],
    'license': "OPL-1",
    'installable': True,
    'application': True,
    'auto_install': False,
}
