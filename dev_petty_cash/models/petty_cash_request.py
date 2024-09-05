# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class petty_cash_request(models.Model):
    _name = 'petty.cash.request'
    _description = 'Petty Cash Management'
    _order = 'name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    @api.model
    def _get_request_by(self):
        employee_id =self.env['hr.employee'].search([('user_id','=',self.env.user.id)])
        return employee_id.id or False
    
    name = fields.Char('Name', default='/', tracking=1)
    note = fields.Text('Notes')
    request_to = fields.Many2one('hr.employee', string='Request To')
    request_by = fields.Many2one('hr.employee', string='Request By', default=_get_request_by)
    payment_journal_id = fields.Many2one('account.journal', string='Payment Journal', domain="[('is_petty_cash', '=', True)]")
    petty_journal_id=  fields.Many2one('account.journal', string='Petty Cash Journal', domain="[('is_petty_cash', '=', True)]", tracking=2)
    date = fields.Date('Date', copy=False, default=fields.Datetime.now)
    request_amount = fields.Monetary('Request Amount', tracking=2)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self:self.env.company.currency_id)
    user_id = fields.Many2one('res.users', string='User', default=lambda self:self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self:self.env.company)
    state = fields.Selection(string='State', selection=[('draft', 'Draft'),
                                                        ('request', 'Requested'),
                                                        ('approve', 'Approved'),
                                                        ('cancel','Cancel'),
                                                        ('reject','Reject')], default='draft', tracking=4)
    payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
    balance = fields.Monetary('Balance', compute='_get_balance')
    
    @api.onchange('payment_id')
    def _get_balance(self):
        for request in self:
            request.balance = request.balance
            if request.payment_id and request.payment_id.move_id:
                move_id = request.payment_id.move_id
                account_id = request.petty_journal_id.default_account_id
                line_id = move_id.line_ids.filtered(lambda t: t.account_id.id == account_id.id)
                request.balance = abs(line_id.amount_residual_currency)
                    
        
    
    
    def create_payment(self):
        payment_method_id= self.env['account.payment.method'].search([('name','=','Manual')],limit=1)
        if not payment_method_id:
            payment_method_id= self.env['account.payment.method'].search([],limit=1)
        vals={
            'payment_type':'inbound',
            'partner_id':self.company_id.partner_id.id or False,
            'destination_account_id':self.petty_journal_id.default_account_id.id or False,
            'is_internal_transfer':True,
            'company_id':self.company_id and self.company_id.id or False,
            'amount':self.request_amount or 0.0,
            'currency_id':self.currency_id and self.currency_id.id or False,
            'journal_id':self.payment_journal_id and self.payment_journal_id.id or False,
#            'payment_method_id':payment_method_id and payment_method_id.id or False,
            'destination_journal_id':self.petty_journal_id.id or False,
        }
        payment_id = self.env['account.payment'].sudo().create(vals)
        payment_id.action_post()
        self.payment_id= payment_id and payment_id.id or False
    
    def action_request(self):
        if self.request_amount <= 0:
            raise ValidationError(_('Request Amount must be positive.'))
        self.state='request'
    
    def action_approve(self):
        self.create_payment()
        self.state='approve'
    
    def action_cancel(self):
        self.state='cancel'
    
    def action_reject(self):
        self.state= 'reject'
    
    def action_draft(self):
        self.state = 'draft'
        
        
    def unlink(self):
        for request in self:
            if request.state != 'draft':
                raise ValidationError(_("You can delete Petty request in draft state only."))
        return super(petty_cash_request, self).unlink()
        
    @api.model
    def create(self, vals):
        vals.update({
            'name': self.env['ir.sequence'].next_by_code('petty.cash.request') or '/',
			
        })
        return super(petty_cash_request, self).create(vals)

#class account_payment(models.Model):
#    _inherit='account.payment'
#    
#    @api.model
#    def create(self,vals):
#        res = super(account_payment,self).create(vals)
#        return res        

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
