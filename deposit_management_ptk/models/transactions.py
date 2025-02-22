from odoo import fields, api, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class Transactions(models.Model):
    _name = 'bank.transaction'
    _description = 'bank transactions'
    _order = "id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Many2one('res.partner', string='Customer', required=True)
    bank_id = fields.Many2one('bank.bank', string='Bank', required=True,
                              default=lambda self: self.env.user.bank_id.id)
    amount = fields.Float(string='Amount')
    balance = fields.Float(string='Balance', compute='get_final_bank_balance')
    trans_date = fields.Datetime(
        string='Date', default=datetime.now(), readonly=True)
    reference = fields.Char(string='Reference', default='New', readonly=True)
    remarks = fields.Char(string='Remarks')
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done')], default='draft')
    type = fields.Selection([('withdrawal', 'Withdrawal'), ('deposit', 'Deposit')],
                            string='Transaction Type', default='withdrawal', required=True)

    def transaction_done(self):
        if self.type == 'withdrawal' and self.name.balance < self.amount:
            raise UserError('You are trying to withdraw more than you own')
        else:
            self.state = 'done'
            self.env.ref(
                "deposit_management_ptk.bank_transaction_email").send_mail(self.id)

    @api.depends('amount', 'name', "trans_date")
    def get_final_bank_balance(self):
        trans = self.env['bank.transaction']
        for record in self:
            all_transactions = trans.search([
                ('bank_id', '=', record.bank_id.id),
                ('name', '=', record.name.id),
                ('state', '=', 'done'),
                ('trans_date', '<=', record.trans_date)
            ])
            all_deposit = sum(all_transactions.filtered(
                lambda lm: lm.type == 'deposit').mapped('amount'))
            all_withdrawal = sum(all_transactions.filtered(
                lambda lm: lm.type == 'withdrawal').mapped('amount'))

            record['balance'] = (
                all_deposit - all_withdrawal
            ) or 0.00

    @api.model
    def create(self, vals):
        vals['reference'] = self.env['ir.sequence'].next_by_code(
            'bank.transaction')
        res = super(Transactions, self).create(vals)
        return res
