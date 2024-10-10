# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

{
    'name': 'Petty Cash Management, Petty Cash Request, Petty Cash Expense',
    'version': '-2024.10.09-17:55',
    'sequence': 1,
    'category': 'Accouting',
    'description':
        """
        This Module add below functionality into odoo

        1.Petty Cash Management
        
        Odoo Petty Cash Management
Efficient Petty Cash System
Petty Cash Handling in Odoo
Odoo Petty Cash Module
Streamlined Petty Cash Management
Petty Cash Workflow in Odoo
Odoo Petty Cash Control
Petty Cash Tracking and Reporting
Odoo Petty Cash Expenses
Petty Cash Reconciliation in Odoo
Odoo Petty Cash Fund Management
Petty Cash Handling Procedures
Odoo Petty Cash Register
Petty Cash Accountability in Odoo
Odoo Petty Cash Expense Management \n


odoo app allow Petty Cash Management, Petty Cash Request, Petty cash expense, Petty Cash Workflow approval process, Petty Cash Request balance, Petty Cash Expense Remaing Balance, Petty Cash due balance, Petty Cash user wise allocation, Cash flow Petty Cash management in odoo

    """,
    'summary': 'odoo app allow Petty Cash Management, Petty Cash Request, Petty cash expense, Petty Cash Workflow approval process, Petty Cash Request balance, Petty Cash Expense Remaing Balance, Petty Cash due balance, Petty Cash user wise allocation, Cash flow Petty Cash management in odoo',
    'depends': ['account','hr'],
    'data': ['security/security.xml',
             'security/ir.model.access.csv',
             'views/petty_cash_request_views.xml',
             'data/ez_sequence.xml',
             'report/print_pettycash_template.xml',
             'report/print_pettycash_menu.xml',
             'report/print_pettycash_exp_template.xml',
             'views/petty_cash_kanban_views.xml',            
             'views/petty_cash_expense_views.xml',],
    'demo': [],
    'test': [],
    'css': [],
    'qweb': [],
    'js': [],
    'images': ['images/main_screenshot.gif'],
    'installable': True,
    'application': True,
    'auto_install': False,
    
    # author and support Details =============#
    'author': 'DevIntelle Consulting Service Pvt.Ltd - Alconsoft',
    'website': 'http://www.devintellecs.com',    
    'maintainer': 'DevIntelle Consulting Service Pvt.Ltd', 
    'support': 'devintelle@gmail.com',
    'price':45.0,
    'currency':'EUR',
    #'live_test_url':'https://youtu.be/A5kEBboAh_k',
    'pre_init_hook' :'pre_init_check'
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
