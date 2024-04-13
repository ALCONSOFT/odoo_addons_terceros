# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).
from datetime import datetime

from odoo import models, fields, api
from odoo.exceptions import UserError


class PurchaseReturn(models.TransientModel):
    _name = 'purchase.return'
    _description = "Return Order Of Purchase Order"

    @api.model
    def default_get(self, fields_list):
        res = super(PurchaseReturn, self).default_get(fields_list)
        if 'knk_purchase_order_id' in fields_list:

            purchase_order = self.env['purchase.order'].browse(
                res['knk_purchase_order_id'])
            res['user_id'] = purchase_order.user_id.id
            res['company_id'] = purchase_order.company_id.id
        return res

    def _get_value_order_line(self):

        active_id = self._context.get('active_id')
        active_model = self.env['purchase.order'].browse(active_id)
        values_list = []
        for lines in active_model.order_line:
            values_list.append([0, 0, {
                'knk_product_id': lines.product_id.id,
                'knk_product_qty': 0,

            }])
        return values_list

    knk_purchase_order_id = fields.Many2one("purchase.order")
    knk_purchase_return_lines_ids = fields.One2many('purchase.return.line',
                                                    'knk_purchase_return_id',
                                                    string="Product", default=_get_value_order_line)
    note = fields.Text()
    date_of_return = fields.Datetime(string="Date Of Return",
                                     default=datetime.today(),
                                     required=True)
    user_id = fields.Many2one(
        'res.users', string='Purchase Representative')
    company_id = fields.Many2one(
        'res.company', 'Company',
        required=True,)

    def return_purchase(self):
        return_lines = []
        for line in range(len(self.knk_purchase_return_lines_ids)):
            if (
                self.knk_purchase_return_lines_ids[line].knk_product_qty > self.knk_purchase_order_id.order_line[line]
                .knk_purchase_balanced_qty or
                self.knk_purchase_return_lines_ids[line].knk_product_qty > self.knk_purchase_order_id.order_line[line].qty_received
            ):

                raise UserError(
                    "Return quantity cannot be more than Delivered Quantity"
                )
        for lines in self.knk_purchase_return_lines_ids:

            return_line_vals = {
                'knk_product_id': lines.knk_product_id.id,
                'knk_product_qty': lines.knk_product_qty,
                'reason_to_return': lines.reason_to_return
            }
            return_lines.append((0, 0, return_line_vals))
        return_order = {'partner_id': self.knk_purchase_order_id.partner_id.id,
                        'user_id': self.user_id.id,
                        'company_id': self.company_id.id,
                        'date_of_return': self.date_of_return,
                        'knk_purchase_order_id': self.knk_purchase_order_id.id,
                        'knk_purchase_order_return_line_ids': return_lines,
                        'note': self.note}
        return_order_id = self.env['purchase.order.return'].create(
            return_order)
        return_order_id.button_confirm()


class PurchaseReturnLine(models.TransientModel):
    _name = 'purchase.return.line'
    _description = "Return Order Line From Purchase Order view"
    _rec_name = 'knk_product_id'

    knk_purchase_return_id = fields.Many2one('purchase.return')
    knk_product_id = fields.Many2one(
        'product.product', string="Product", required=True)
    knk_product_qty = fields.Float(string="Quantity")
    move_id = fields.Many2one('stock.move', "Move")
    reason_to_return = fields.Char(string="Reason")



    



