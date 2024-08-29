from odoo import models, fields, api
from odoo.exceptions import ValidationError



class RejectWizard(models.TransientModel):
   _name = 'reject.wizard'
   _description = "Payment Reject Wizard"


   reason = fields.Text('Reajection Reason')
   order_id = fields.Many2one('account.payment', string="Order")



   def reject_reason(self):
        if not self.order_id:
            raise ValidationError(('Payment not found!\n Refresh the page and try again.'))
        if self.order_id and self.order_id.current_waiting_approval_line_id and not self.order_id.current_waiting_approval_line_id.status and not self.order_id.current_approval_state:
            self.order_id.reject_date = fields.Datetime.now()
            self.order_id.rejected_user_id = self.env.user.id
            self.order_id.reject_reason = self.reason if self.reason else False
            self.order_id.state = 'reject'
            self.order_id.is_rejected = True
            template = self.env.ref('bi_payment_dynamic_approval.payment_reject_email_notification')
            if template:
                if self.order_id.is_sales_person_in_cc:
                    template.email_cc = self.order_id.user_id.email if self.order_id.user_id else False
                mail = template.send_mail(int(self.order_id.id))
                if mail:
                    mail_id = self.env['mail.mail'].browse(mail)
                    mail_id[0].sudo().send()
          
        return True