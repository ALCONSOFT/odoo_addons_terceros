# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

{
    "name": "Purchase Approval Rules",
    'summary': 'Purchase order approval rules',
    "version": "16.0.1.1",
    "category": "Inventory/Purchase",
    "license": "OPL-1",
    "summary": "This module allow to approve purchase order in a flow of action of various stakeholder on the basis of their roles | sale approve| purchase | purchase approve | approval rules | purchase order approval | Approval Rules | Purchase Approval| Purchase Order Rules | Purchase Order Approval | Purchase Approve | Sale Approval |",
    "description": "Purchase Approval Rules module allow to approve purchase order in a flow of action of various stakeholder on the basis of their roles.",
    "website": "https://www.kanakinfosystems.com",
    "author": "Kanak Infosystems LLP.",
    "depends": ["hr", "purchase"],
    'images': ['static/description/banner.jpg'],
    "data": [
        "security/ir.model.access.csv",
        "data/mail_template.xml",
        "views/approval_config.xml",
        "views/purchase_order_config.xml",
        "views/purchase_view.xml",
        "wizard/custom_warning_view.xml"
    ],
    'sequence': 1,
    "installable": True,
    "price": 30,
    "currency": "EUR",
}
