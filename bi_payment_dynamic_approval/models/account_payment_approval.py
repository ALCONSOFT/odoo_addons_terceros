from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class AccountPaymentApproval(models.Model):

    _name = 'account.payment.approval'
    _description = "Account Payment Approval"


    name = fields.Char(string='Name')
    minimun_amount = fields.Float(string='Minimum Amount')
    sale_person_always = fields.Boolean(string="Buyer Always In CC")
    payment_access_ids = fields.One2many(
        'account.payment.line',
        'payment_access_id', 
        string='Approval',
        copy=False,
        )
    approval = fields.Char(string='Approval Level')
    approval_id = fields.Many2one(
        'res.users',
        string='Approval Level ',
        )
    data_id = fields.Many2one('account.payment', string='Data')
    user_name = fields.Char(string='Name ')
    approval_id = fields.Many2one(string='Approval Level ', comodel_name='account.payment.line', ondelete='restrict')
    user_id = fields.Many2one(string='Users', comodel_name='res.users', ondelete='restrict')
    group_id = fields.Many2one(string='Groups', comodel_name='res.groups', ondelete='restrict')
    groups_name = fields.Char(string='Groups ')
    status_approval = fields.Boolean(string='Status')
    approve_date = fields.Date(string='Approve Date')
    approved_by = fields.Char(string='Approved By')


    @api.onchange('payment_access_ids')
    def _onchange_payment_access_ids(self):
        level = []
        for approval in self.payment_access_ids:
            if approval.level in level:
                raise ValidationError(_('Approval Levels must be unique!'))
            level.append(approval.level)

    
class AccountPaymentLine(models.Model):

    _name = 'account.payment.line'
    _rec_name = 'level'
    _description = "Account Payment Line"
 

    payment_access_id = fields.Many2one(
        comodel_name='account.payment.approval',
        string='Payment Approval Level',
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade")
   
    level = fields.Integer(string='Level')
    group_approve = fields.Selection(string='Approve By', selection=[
                                     ('group', 'Group'), ('user', 'User')], default='user')
    group_ids = fields.Many2many('res.groups',string="Groups")
    user_ids = fields.Many2many('res.users',string="Users")
    state = fields.Boolean('State')
    payment_approval_id = fields.Many2one('account.payment.approval', string='Approvals')
    level_id = fields.Many2one(
        string='Approval level', comodel_name='account.payment.approval', ondelete='restrict')
    order_id = fields.Many2one('account.payment', string='Order')
    approval_level = fields.Integer('Approval Level')