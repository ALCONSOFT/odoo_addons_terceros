from odoo import _, api, fields, models, tools

class PaymentLine(models.Model):

    _name = 'payment.line'
    _description = "Payment Line"


    approval_line_id = fields.Many2one(
        'account.payment.line', string='Purchase Approval Line')
    payment_id = fields.Many2one('account.payment', string='Purchase Order')
    level = fields.Integer(string='Level')
    user_ids = fields.Many2many(
        'res.users', 'rel_account_payment_line_users',
        string='Users')
    group_ids = fields.Many2many(
        'res.groups', 'rel_account_payment_line_groups',
        string='Groups')
    status = fields.Boolean(string="Status")
    approved_date = fields.Datetime(string="Approved Date")
    approved_id = fields.Many2one('res.users', string='Approved By')
    payment_access_id = fields.Many2one(comodel_name='account.payment.approval', string='Purchase Approval Level')
    level_id = fields.Many2one(
        string='Approval level', comodel_name='account.payment.approval', ondelete='restrict')    
   