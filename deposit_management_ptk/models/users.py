from odoo import fields, api, models, _


class Users(models.Model):
    _inherit = 'res.users'
    
    bank_id = fields.Many2one('bank.bank', string='Bank ID')
    balance = fields.Float(string='Balance')