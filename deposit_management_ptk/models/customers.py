from odoo import fields, api, models, _

class Customers(models.Model):
    _inherit = 'res.partner'
    
    bank_id = fields.Many2one('bank.bank', string='Bank ID', default=lambda self: self.env.user.bank_id.id)
    balance = fields.Float(string='Balance', compute='_get_final_bank_balance')

    def _get_final_bank_balance(self):
        trans = self.env['bank.transaction']
        for record in self:
            all_transactions = trans.search([('bank_id', '=', record.bank_id.id), ('name', '=', record.id)])
            all_deposit = sum(all_transactions.filtered(lambda lm: lm.type == 'deposit').mapped('amount'))
            all_withdrawal = sum(all_transactions.filtered(lambda lm: lm.type == 'withdrawal').mapped('amount'))
        
            record['balance'] = (all_deposit - all_withdrawal) or 0.00
            
    
    def redirect_to_transactions(self):
    
        return {
            'name': _('Transaction History'),
            'view_mode': 'tree',
            'res_model': 'bank.transaction',
            'view_id': self.env.ref('deposit_management.bank_transaction_list_view').id,
            'type': 'ir.actions.act_window',
            'domain': [('name', '=', self.id)]
        }