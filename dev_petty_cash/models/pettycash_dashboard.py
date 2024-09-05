# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models, _
#slide.channel.view

class ProductTemplate(models.Model):
    _inherit = "account.journal"
	
    is_petty_cash = fields.Boolean(string='Is Petty Cash')
    total_request = fields.Integer(string='Request', compute="compute_request", copy=False)
    total_expense = fields.Integer(string='Expense', compute="compute_expense", copy=False)
    approve_state = fields.Integer(string='Approve', compute="compute_approve_state", copy=False)
    request_state = fields.Integer(string='Pending', compute="compute_request_state", copy=False)
    total_done_state = fields.Integer(string='Done', compute="compute_done_state", copy=False)
    total_expense_state = fields.Integer(string='Pending', compute="compute_expense_total_state", copy=False)
    total_request_amount = fields.Float(string='Request Amount', compute="compute_total_request_amount", copy=False)
    total_expense_amount = fields.Float(string='Expense Amount', compute="compute_total_expense_amount", copy=False)

    def action_create_new_request(self):
        ctx = self._context.copy()
        ctx.update({'default_petty_journal_id': self.id })
        view_id = self.env.ref("dev_petty_cash.view_petty_cash_request_form").id
        return {
	        'name': _('Create Petty Cash Request'),
	        'type': 'ir.actions.act_window',
	        'view_type': 'form',
	        'view_mode': 'form',
	        'res_model': 'petty.cash.request',
	        'view_id': view_id,
	        'context': ctx,
	    }

    def action_create_new_expense(self):
        ctx = self._context.copy()
        ctx.update({'default_petty_journal_id': self.id })
        view_id = self.env.ref("dev_petty_cash.view_petty_cash_expense_form").id
        return {
            'name': _('Create Petty Cash Expense'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'petty.cash.expense',
            'view_id': view_id,
            'context': ctx,
        }


    def compute_request(self):
        for data in self:
            allrequest_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id)])
            data.total_request = allrequest_ids


    def action_get_all_request(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_request_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id)])
            return {
                'name': 'Total Request',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_request_ids.ids)]
            }

    def compute_approve_state(self):
        for data in self:
            approve_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'approve')])
            data.approve_state = approve_ids


    def action_get_approve(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_approve_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'approve')])
            return {
                'name': 'Approve Request',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_approve_ids.ids)]
            }

    def compute_request_state(self):
        for data in self:
            request_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', 'in', ['request','draft'])])
            data.request_state = request_ids


    def action_get_pending(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_pending_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', ['request','draft'])])
            return {
                'name': 'Pending Request',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_pending_ids.ids)]
            }

    def compute_total_request_amount(self):
        for data in self:
            request_amount_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'approve')])
            amount = sum(line.request_amount for line in request_amount_ids)
            data.total_request_amount = amount
           

    def action_get_approve_request_amount(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_approve_amount_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'approve')])
            return {
                'name': 'Approve Amount',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_approve_amount_ids.ids)]
            }

    def compute_total_expense_amount(self):
        for data in self:
            exp_amount_ids = self.env['petty.cash.expense'].search([('petty_journal_id', '=', data.id), ('state', '=', 'done')])
            amount = sum(line.expense_amount for line in exp_amount_ids)
            data.total_expense_amount = amount
           

    def action_get_done_expense_amount(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form').id
        for data in self:
            total_done_amount_ids = self.env['petty.cash.expense'].search([('petty_journal_id', '=', data.id), ('state', '=', 'done')])
            return {
                'name': 'Approve Amount',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.expense',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_done_amount_ids.ids)]
            }



    def compute_expense(self):
        for data in self:
            all_expense_ids = self.env['petty.cash.expense'].search_count([('petty_journal_id', '=', data.id)])
            data.total_expense = all_expense_ids


    def action_get_all_expense(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form').id
        for data in self:
            total_expense_ids = self.env['petty.cash.expense'].search([('petty_journal_id', '=', data.id)])
            return {
                'name': 'Total Expense',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.expense',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_expense_ids.ids)]
            }

    def compute_done_state(self):
        for data in self:
            done_state_ids = self.env['petty.cash.expense'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'done')])
            data.total_done_state = done_state_ids


    def action_get_done_state(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form').id
        for data in self:
            total_done_ids = self.env['petty.cash.expense'].search([('petty_journal_id', '=', data.id), ('state', '=', 'done')])
            return {
                'name': 'Done Expense',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.expense',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_done_ids.ids)]
            }

    def compute_expense_total_state(self):
        for data in self:
            total_expense_state_ids = self.env['petty.cash.expense'].search_count(
                [('petty_journal_id', '=', data.id), ('state', 'in', ['payment','confirm','draft'])])
            data.total_expense_state = total_expense_state_ids


    def action_get_expense_state(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form').id
        for data in self:
            total_paymnet_ids = self.env['petty.cash.expense'].search([('petty_journal_id', '=', data.id), ('state', 'in', ['payment','confirm','draft'])])
            return {
                'name': 'Pending Expense',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.expense',
                'views': [(tree_id, 'tree'),
                          (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_paymnet_ids.ids)]
            }


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:





