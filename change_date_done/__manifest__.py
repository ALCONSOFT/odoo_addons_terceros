# -*- coding: utf-8 -*-
{
    "name": "Change Date done",
    "version": "14.0",
    "category": "Tools",
    "author": "Simple Apps",
    "application": True,
    "installable": True,
    "auto_install": False,
    "depends": [
    	"account",
        "sale",
        "stock",
    ],
    "data": [
		'security/ir.model.access.csv',
		'views/views.xml',
    ],
    "summary": "Change date done of Invoice, Picking. invoice date, picking date, change date in bulk",
    
    "description": """
    Change date done of Invoice, Picking
""",
    "images": [
        "static/description/screen.png",
    ],
    "price": "10.0",
    "currency": "EUR",
}