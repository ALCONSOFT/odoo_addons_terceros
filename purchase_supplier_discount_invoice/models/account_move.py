# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
import odoo.addons.decimal_precision as dp
from odoo.tools import float_is_zero

class account_move(models.Model):
    _inherit = 'account.move'


    @api.depends('discount_amount','discount_method')
    def _calculate_discount(self):
        res = discount = 0.0
        for self_obj in self:
            if self_obj.discount_method == 'fix':
                res = self_obj.discount_amount
            elif self_obj.discount_method == 'per':
                total = 0.0
                for line in self.invoice_line_ids:
                    if line.exclude_from_invoice_tab == False:
                        total += line.price_unit 
                    res = total * (self_obj.discount_amount/ 100)
            else:
                res = discount
            return res

    def _calculate_discount_sec(self, amount_untaxed):
        res = discount = 0.0
        for self_obj in self:
            if self_obj.discount_method == 'fix':
                res = self_obj.discount_amount
            elif self_obj.discount_method == 'per':
                res = amount_untaxed * (self_obj.discount_amount/ 100)
            else:
                res = discount
            return res


    @api.depends(
        'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state',
        'line_ids.full_reconcile_id','discount_method','discount_amount')
    def _compute_amount(self):
        for move in self:

            if move.payment_state == 'invoicing_legacy':
                # invoicing_legacy state is set via SQL when setting setting field
                # invoicing_switch_threshold (defined in account_accountant).
                # The only way of going out of this state is through this setting,
                # so we don't recompute it here.
                move.payment_state = move.payment_state
                continue

            total_untaxed = 0.0
            total_untaxed_currency = 0.0
            total_tax = 0.0
            total_tax_currency = 0.0
            total_to_pay = 0.0
            total_residual = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            currencies = move._get_lines_onchange_currency().currency_id

            for line in move.line_ids:
                if move.is_invoice():
                    # === Invoices ===

                    if line.display_type == 'tax' or (line.display_type == 'rounding' and line.tax_repartition_line_id):
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type in ('product', 'rounding'):
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type == 'payment_term':
                        # Residual amount.
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            sign = move.direction_sign
            move.amount_untaxed = sign * total_untaxed_currency
            move.amount_tax = sign * total_tax_currency
            move.amount_total = sign * total_currency
            move.amount_residual = -sign * total_residual_currency
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
            move.amount_residual_signed = total_residual
            move.amount_total_in_currency_signed = abs(move.amount_total) if move.move_type == 'entry' else -(sign * move.amount_total)
            res = move._calculate_discount()
            move.discount_amt = res
            


    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')],'Discount Method')
    discount_amount = fields.Float('Discount Amount')

    discount_amt = fields.Float(string='- Discount',  store=True, readonly=True, tracking=True, compute='_compute_amount')

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, tracking=True,
        compute='_compute_amount')

    amount_tax = fields.Monetary(string='Tax', store=True, readonly=True,
        compute='_compute_amount')

    amount_total = fields.Monetary(string='Total', store=True, readonly=True,
        compute='_compute_amount',
        inverse='_inverse_amount_total')

    invoice_line_ids = fields.One2many(  # /!\ invoice_line_ids is just a subset of line_ids.
        'account.move.line',
        'move_id',
        string='Invoice lines',
        copy=False,
        readonly=True,
        domain=[('display_type', 'in', ('product', 'line_section', 'line_note')),('exclude_from_invoice_tab','=',False)],
        states={'draft': [('readonly', False)]},
    )



    @api.model_create_multi
    def create(self, vals_list):
        result = super(account_move,self).create(vals_list)
        if self._context.get('default_move_type') in ('in_invoice','in_refund','in_receipt'):
            for res in result:
                if res.discount_method and res.discount_amount:
                    if res.state in 'draft':
                        account = False
                        for line in res.invoice_line_ids:
                            if line.product_id:
                                account = line.account_id.id    
                        
                        l = res.line_ids.filtered(lambda s: s.name == "Discount")
                        
                        if len(l or []) == 0 and account:
                            discount_vals = {
                                'account_id': account, 
                                'quantity': 1,
                                'price_unit': -res.discount_amt,
                                'name': "Discount", 
                                'tax_ids':None,
                                'exclude_from_invoice_tab': True,
                            }
                            res.with_context(check_move_validity=False).write({
                                    'invoice_line_ids' : [(0,0,discount_vals)]
                                })
        return result 


    def write(self,vals):
        result = super(account_move,self).write(vals)
        for res in self:
            if res.move_type in ('in_invoice','in_refund','in_receipt') and res.state in 'draft' and res.discount_method in ('fix','per') and res.discount_amount > 0:
                account = False
                for line in res.invoice_line_ids:
                    if line.product_id:
                        account = line.account_id.id
                l = res.line_ids.filtered(lambda s: s.name == 'Discount')
                if len(l or []) == 0 and account:
                    discount_vals = {
                        'account_id': account, 
                        'quantity': 1,
                        'price_unit': -res.discount_amt,
                        'name': "Discount", 
                        'tax_ids':None,
                        'exclude_from_invoice_tab': True,
                    } 
        
                    res.with_context(check_move_validity=False).write({
                            'invoice_line_ids' : [(0,0,discount_vals)]
                        })
        return result  


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    exclude_from_invoice_tab = fields.Boolean(help="Technical field used to exclude some lines from the invoice_line_ids tab in the form view.")



     
