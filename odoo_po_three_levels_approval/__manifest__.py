{
    'name': 'PO Three Level Approval',
    'version': '1.0.1',
    'category': 'Purchases',
    'author': 'FreelancerApps',
    'summary': 'Purchase Order approval : Purchase Manager, Finance Manager, Director Approval multi level approve three level approve purchase order approve purchase order three level approval multi-level approval purchase_order_triple_approval double Approve double Approval Tripple Approve Purchase Tripple Approval Process Sale Order Tripple Approval payslip_tripple_approval Payslip Tripple Approval invoice triple approval sale order triple approval Tripple Approval Sales Quote sale_tripple_approv generate barcode product auto Restrict Read Only User Hide Any Menu Restrict User Menus multi level approve three level approve Tripple Approve Purchase Tripple Approval Project Checklist Task Checklist website document attachment product attachment',
    "description": """
PO Three Level Approval
-----------------------
Purchase Order approval : Purchase Manager, Finance Manager, Director Approval

tag: multi level approve three level approve purchase order approve purchase order three level approval multi-level approval purchase_order_triple_approval
double Approve double Approval Tripple Approve Purchase Tripple Approval Process Sale Order Tripple Approval payslip_tripple_approval Payslip Tripple Approval
invoice triple approval sale order triple approval Tripple Approval Sales Quote sale_tripple_approv 

generate barcode product auto Restrict Read Only User Hide Any Menu Restrict User Menus multi level approve three level approve Tripple Approve Purchase Tripple Approval Project Checklist Task Checklist
website document attachment product attachment
""",
    'depends': ['base', 'purchase'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data_file.xml',
        'views/res_company_view.xml',
        'views/purchase_view.xml',
        'views/res_config_settings_views.xml',
        'wizard/purchase_order_refuse_view.xml',
        'report/purchase_order_templates.xml',
    ],
    'images': ['static/description/odoo_po_three_level_approval_banner.gif'],
    'price': 19.99,
    'currency': 'USD',
    'license': 'OPL-1',
    'installable': True,
    'application': False,
    'auto_install': False,
}
