from odoo import fields, api, models, _

class Banks(models.Model):
    _name = 'bank.bank'
    _description = 'Banks'
    
    name = fields.Char(string="Bank Name", required=True)
    code = fields.Char(string='Code', default='New', readonly=True)
    balance = fields.Float(string='Balance', compute='_get_final_bank_balance')
    partner_id = fields.Many2one('res.partner', string='Address')
    
    _sql_constraints = [
        ('unique_bank_name', 'unique(name)', 'Bank Name already exist, please provide another')
    ]
    
    @api.model
    def create(self, vals):
        vals['code'] = self.env['ir.sequence'].next_by_code('bank.bank')
        res = super(Banks, self).create(vals)
        return res

    api.depends('amount', 'name')
    def _get_final_bank_balance(self):
        trans = self.env['bank.transaction']
        for record in self:
            all_transactions = trans.search([('bank_id', '=', record.id)])
            all_deposit = sum(all_transactions.filtered(lambda lm: lm.type == 'deposit').mapped('amount'))
            all_withdrawal = sum(all_transactions.filtered(lambda lm: lm.type == 'withdrawal').mapped('amount'))
        
            record['balance'] = (all_deposit - all_withdrawal) or 0.00

        
