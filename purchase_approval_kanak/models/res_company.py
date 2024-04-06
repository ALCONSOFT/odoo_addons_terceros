# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    purchase_order_approval_rule_id = fields.Many2one('purchase.order.approval.rule', string='Purchase Order Approval Rules')
    purchase_order_approval = fields.Boolean(string='Purchase Order Approval By Rule')
