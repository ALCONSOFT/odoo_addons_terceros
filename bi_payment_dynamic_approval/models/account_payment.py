from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError



class AccountPayment(models.Model):

    _inherit = 'account.payment'
    _description = "Account Payment"



    def read(self, fields=None, load='_classic_read'):
        if self.env.user.company_id.dynamic_approval:
            data = self.search([]).filtered(
                lambda l: l.is_approval_reject_button)
            data._compute_is_approval_reject_button()
        return super(AccountPayment, self).read(fields=fields, load=load)

    payment_access_id = fields.Many2one(
        comodel_name='account.payment.approval', string='Payment Approval Level')
    level_data = fields.Char(string='Approval Level')
    current_approval_state = fields.Boolean(
        'Current approval state', copy=False)
    approved_user_ids = fields.Many2many(
        'res.users',  'approved_user_sale_order_rel', string='Approved Users', copy=False)
    user_ids = fields.Many2many(
        'res.users', 'rel_account_payment_users', string='Users')
    group_ids = fields.Many2many(
        'res.groups', 'rel_account_payment_groups', string='Groups')
    reject_date = fields.Datetime('Reject Date', copy=False)
    rejected_user_id = fields.Many2one(
        'res.users', string='Reject By', copy=False)
    reject_reason = fields.Text('Reject Reason', copy=False)
    approval_line_ids = fields.One2many(
        'payment.line', "payment_id", string="Approval Level ")
    state = fields.Selection(selection=[
        ('draft', 'Draft'),
        ('waiting', 'Waiting For Approval'),
        ('posted', 'Posted'),
        ('reject', 'Reject'),
        ('cancel', 'Cancelled'),
    ],default='draft', string="State")
    current_waiting_approval_line_id = fields.Many2one(
        'payment.line', string='Current approval line', copy=False)
    is_display = fields.Boolean()
    is_approval_reject_button = fields.Boolean(
        'Approval Reject button', default=False, compute='_compute_is_approval_reject_button')
    is_sales_person_in_cc = fields.Boolean(related='payment_access_id.sale_person_always')
    payment_approved_ids = fields.One2many(
        'account.payment.line', 'order_id', string='PO Approval Details')
    is_rejected = fields.Boolean('Reject Order', default=False, copy=False)
    all_level_approved = fields.Boolean(
        'All Level Approved', default=False, compute='_compute_all_level_approved')



    @api.depends('approval_line_ids')
    def _compute_all_level_approved(self):
        for record in self:
            if record.approval_line_ids and all(record.approval_line_ids.mapped('state')):
                record.all_level_approved = True
            else:
                record.all_level_approved = False


    @api.depends('approved_user_ids', 'user_ids')
    def _compute_is_approval_reject_button(self):
        for record in self:
            record.is_display = False
            record.is_approval_reject_button = False
            if record.user_ids:
                if self.env.user.id in record.user_ids.ids:
                    record.is_display = True
                    record.is_approval_reject_button = True
            elif record.group_ids:
                if (set(record.group_ids.ids).issubset(set(self.env.user.groups_id.ids))):
                    record.is_approval_reject_button = True
                    record.is_display = True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        super(AccountPayment, self).action_cancel()


    def action_draft(self):
        self.write({'state': 'draft'})
        super(AccountPayment, self).action_draft()


    def button_cancel(self): 
        return {
            'name': _('Payment Reject'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'reject.wizard',
            'target': 'new',
            'context': {'default_order_id': self.id}
        }


    def approve_btn(self):
            if self.current_waiting_approval_line_id and not self.current_waiting_approval_line_id.status and not self.current_approval_state:
                self.current_approval_state = True
                self.current_waiting_approval_line_id.status = True
                self.current_waiting_approval_line_id.approved_date = fields.Datetime.now()
                self.current_waiting_approval_line_id.approved_id = self.env.user.id
                self.approved_user_ids = [(4, self.env.user.id)]
                self.action_post()
            return True


    def _prepare_approved_line(self, line):
        if line:
            return {
                'level': line.level,
                'user_ids': line.user_ids.ids if line.user_ids else [],
                'group_ids': line.group_ids.ids if line.group_ids else [],
            }


    
    def action_post(self):
        if not self.payment_access_id or self.amount <= self.payment_access_id.minimun_amount :
             self.write({'state': 'posted'})
             super(AccountPayment, self).action_post()
        else:
            for order in self:
                if self.payment_access_id:
                    if self.payment_access_id and not self.approval_line_ids:
                        if not self.payment_access_id.payment_access_ids:
                            raise ValidationError(_('No any approval level found!'))
                        approval_lines = []
                        for record in self.payment_access_id.payment_access_ids:
                            approval_lines.append(
                                (0, 0, self._prepare_approved_line(record)))
                        if approval_lines:
                            self.write({'approval_line_ids': approval_lines})
                            template = self.env.ref(
                            "bi_payment_dynamic_approval.payment_approval_email_notification")
                        if template:
                            values = template.sudo().generate_email(self.id, [
                                'subject', 'body_html', 'email_from', 'email_to', 'partner_to', 'email_cc', 'reply_to', 'scheduled_date'])
                            
                            if order.payment_access_id.sale_person_always:
                                values['email_cc'] = self.user_id.email or ''
                                mail_mail_obj = self.env['mail.mail']
                                msg_id = mail_mail_obj.sudo().create(values)
                                if msg_id:
                                    msg_id.sudo().send()
                            else:
                                mail_mail_obj = self.env['mail.mail']
                                msg_id = mail_mail_obj.sudo().create(values)
                                if msg_id:
                                    msg_id.sudo().send()
                    if self.approval_line_ids:
                        if not all(self.approval_line_ids.mapped('status')):
                            approval_level = 0
                            sorted_approval_lines = sorted(self.approval_line_ids, key=lambda l: l.level)
                            filtered_approval_lines = filter(lambda l: not l.status, sorted_approval_lines)
                            for approval in filtered_approval_lines:
                                if approval_level <= int(approval.level) and (not self.current_waiting_approval_line_id or self.current_waiting_approval_line_id.status) and (self.current_approval_state or approval_level == 0):
                                    approval_level = approval.level
                                    self.user_ids = False
                                    self.group_ids = False
                                    self.level_data = str(approval.level)
                                    self.user_ids = approval.user_ids.ids
                                    self.group_ids = approval.group_ids.ids
                                    self.state = 'waiting'
                                    self.current_waiting_approval_line_id = approval.id
                                    self.current_approval_state = False
                        else:
                            self.state = 'posted'
                            template = self.env.ref(
                            "bi_payment_dynamic_approval.payment_confirm_email_notification")
                            if template:
                                values = template.sudo().generate_email(self.id, [
                                    'subject', 'body_html', 'email_from', 'email_to', 'partner_to', 'email_cc', 'reply_to', 'scheduled_date'])
                                for order in self:
                                    if order.payment_access_id.sale_person_always:
                                        values['email_cc'] = self.user_id.email or ''
                                        mail_mail_obj = self.env['mail.mail']
                                        msg_id = mail_mail_obj.sudo().create(values)
                                        if msg_id:
                                            msg_id.sudo().send()
                                    else:
                                        mail_mail_obj = self.env['mail.mail']
                                        msg_id = mail_mail_obj.sudo().create(values)
                                        if msg_id:
                                            msg_id.sudo().send()
                            return super(AccountPayment, self).action_post()
                else:
                    return super(AccountPayment, self).action_post()


    @api.depends('approved_user_ids', 'user_ids')
    def _compute_is_approval_reject_button(self):
        for record in self:
            record.is_display = False
            record.is_approval_reject_button = False
            if record.user_ids:
                if self.env.user.id in record.user_ids.ids:
                    record.is_display = True
                    record.is_approval_reject_button = True
            elif record.group_ids:
                if (set(record.group_ids.ids).issubset(set(self.env.user.groups_id.ids))):
                    record.is_approval_reject_button = True
                    record.is_display = True

   
 

    @api.depends('approval_line_ids')
    def _compute_all_level_approved(self):
        for record in self:
            if record.approval_line_ids and all(record.approval_line_ids.mapped('status')):
                record.all_level_approved = True
            else:
                record.all_level_approved = False

  

  