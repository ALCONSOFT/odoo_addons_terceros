from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrderRefuse(models.TransientModel):
    _name = 'purchase.order.refuse'
    _description = 'Purchase Order Refuse'

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    refuse_reason = fields.Text(string='Refused Reason')

    def button_refuse(self):
        for obj in self:
            if not (self.env.user.partner_id.email or obj.purchase_order_id.partner_id.email):
                raise UserError(_("Current User And Supplier Email Id Set Or Not"))
            if obj.purchase_order_id:
                self.env.user.company_id.refuse_mail_template.send_mail(obj.purchase_order_id.id)
                obj.purchase_order_id.write({
                    'state': 'refuse',
                    'refused_user_id': self.env.user.id,
                    'refused_date': fields.Date.context_today(self),
                    'refused_reason': obj.refuse_reason,
                    'dept_manager_id': None,
                    'finance_approval_id': None,
                    'director_approval_id': None,
                    'dept_manager_approve_date': None,
                    'finance_manager_approve_date': None,
                    'director_approve_date': None,
                })
