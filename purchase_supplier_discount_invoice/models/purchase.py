# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
import odoo.addons.decimal_precision as dp
from odoo.tools.misc import formatLang

class purchase_order(models.Model):
    _inherit = 'purchase.order'
       
    @api.depends('discount_amount','discount_method')
    def _calculate_discount(self):
        res=0.0
        discount = 0.0
        for self_obj in self:
            if self_obj.discount_method == 'fix':
                discount = self_obj.discount_amount
                res = discount
            elif self_obj.discount_method == 'per':
                discount = self_obj.amount_untaxed * (self_obj.discount_amount/ 100)
                res = discount
            else:
                res = discount
        return res



    @api.depends('order_line.price_total','discount_amount')
    def _amount_all(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            order.amount_untaxed = sum(order_lines.mapped('price_subtotal'))
            order.amount_total = sum(order_lines.mapped('price_total'))
            order.amount_tax = sum(order_lines.mapped('price_tax'))

            res = self._calculate_discount()
            order.update({'discount_amt' : res,
                          'amount_total': order.amount_untaxed + order.amount_tax-res
                          })


    
    @api.depends('order_line.taxes_id', 'order_line.price_subtotal', 'amount_total', 'amount_untaxed','discount_amount')
    def _compute_tax_totals(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in order_lines],
                order.currency_id,
            )

            res = self._calculate_discount()
            if tax_totals.get('amount_untaxed'):
                tax_totals['amount_untaxed'] = tax_totals['amount_untaxed'] - res
            if tax_totals.get('formatted_amount_total'):
                format_tax_total = tax_totals['amount_untaxed'] + order.amount_tax
                tax_totals['formatted_amount_total'] = formatLang(self.env, format_tax_total, currency_obj=self.currency_id)
            if tax_totals.get('formatted_amount_untaxed'):
                format_total = tax_totals['amount_untaxed']
                tax_totals['formatted_amount_untaxed'] = formatLang(self.env, format_total, currency_obj=self.currency_id)
            groups_by_subtotal = tax_totals.get('groups_by_subtotal', {})
            if bool(groups_by_subtotal):
                _untax_amount = groups_by_subtotal.get('Untaxed Amount', [])
                if bool(_untax_amount):
                    for _tax in range(len(_untax_amount)):
                        if _untax_amount[_tax].get('tax_group_base_amount'):
                            tax_totals.get('groups_by_subtotal', {}).get('Untaxed Amount', [])[_tax].update({
                                'tax_group_base_amount' : _untax_amount[_tax]['tax_group_base_amount'] - res
                            })
                        if _untax_amount[_tax].get('formatted_tax_group_base_amount'):
                            format_total = _untax_amount[_tax]['tax_group_base_amount'] - res
                            tax_totals.get('groups_by_subtotal', {}).get('Untaxed Amount', [])[_tax].update({
                                'formatted_tax_group_base_amount' : formatLang(self.env, format_total, currency_obj=self.currency_id)
                            })
            subtotals = tax_totals.get('subtotals', {})
            if bool(subtotals):
                for _tax in range(len(subtotals)):
                    if subtotals[_tax].get('amount'):
                        tax_totals.get('subtotals', {})[_tax].update({
                            'amount' : subtotals[_tax]['amount'] - res
                        })
                    if subtotals[_tax].get('formatted_amount'):
                        format_total = subtotals[_tax]['amount']
                        tax_totals.get('subtotals', {})[_tax].update({
                            'formatted_amount' : formatLang(self.env, format_total, currency_obj=self.currency_id)
                        })
                
                
            order.tax_totals = tax_totals

    discount_method = fields.Selection(
            [('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
    discount_amount = fields.Float('Discount Amount')
    discount_amt = fields.Monetary(compute='_amount_all',store=True,string='- Discount',digits='Account',readonly=True)
    
    def _prepare_invoice(self):

        res = super(purchase_order,self)._prepare_invoice()
        res.update({'discount_method': self.discount_method,'discount_amount': self.discount_amount,'discount_amt': self.discount_amt})
        return res     
        
class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
            

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:s
