# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, api
from datetime import datetime


class PrintMembership(models.AbstractModel):
    _name = 'report.dev_petty_cash.petty_cash_exp_template'
    _description="Petty Cash Expense Report"

   # def get_date(self, date):
    #    date =  date.strftime('%d-%m-%Y')
    #    return date

    def _get_report_values(self, docids, data=None):
        docs = self.env['petty.cash.expense'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'petty.cash.expense',
            'docs': docs,
            #'get_date': self.get_date,
        }



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
