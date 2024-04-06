from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dept_manager_approve_limit = fields.Float(string='Double Approve Limit', default=0.0)
    finance_approve_limit = fields.Float(default=0.0)
    director_approve_limit = fields.Float(default=0.0)

    three_step_approval = fields.Boolean(default=False)
    set_approval_user_required = fields.Boolean(string='Set Approve User', default=False)
    approve_mail_template = fields.Many2one('mail.template', string='Approve Email Template')
    refuse_mail_template = fields.Many2one('mail.template', string='Refuse Email Template')

    @api.onchange('three_step_approval')
    def _set_template_and_amt(self):
        if self.three_step_approval:
            self.update({
                'approve_mail_template': self.env.ref('odoo_po_three_levels_approval.purchase_order_approval_email_template').id,
                'refuse_mail_template': self.env.ref('odoo_po_three_levels_approval.purchase_order_refuse_email_template').id
            })
        else:
            self.update({'approve_mail_template': False, 'refuse_mail_template': False,
                         'dept_manager_approve_limit': 0.0, 'finance_approve_limit': 0.0, 'director_approve_limit': 0.0})
