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
    
    # Nuevos campos para estados adicionales del flujo de caja chica
    sent_state = fields.Integer(string='Sent', compute="compute_sent_state", copy=False)
    received_state = fields.Integer(string='Received', compute="compute_received_state", copy=False)
    paid_state = fields.Integer(string='Paid', compute="compute_paid_state", copy=False)
    audited_state = fields.Integer(string='Audited', compute="compute_audited_state", copy=False)
    rejected_state = fields.Integer(string='Rejected', compute="compute_rejected_state", copy=False)
    
    # Campo para el saldo total de la caja chica
    petty_cash_balance = fields.Monetary(string='Saldo de Caja Chica', compute="compute_petty_cash_balance", copy=False)
    
    # Campo adicional para solicitudes aprobadas pendientes de pago
    pending_approved_amount = fields.Monetary(string='Monto Aprobado Pendiente', compute="compute_pending_approved_amount", copy=False)

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
        view_id = self.env.ref("dev_petty_cash.view_petty_cash_expense_form2").id
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
                [('petty_journal_id', '=', data.id), ('state', '=', 'approved')])
            data.approve_state = approve_ids


    def action_get_approve(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_approve_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'approved')])
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
                [('petty_journal_id', '=', data.id), ('state', 'in', ['requested','draft'])])
            data.request_state = request_ids


    def action_get_pending(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_pending_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', 'in', ['requested','draft'])])
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
            # Cambiar para usar los mismos estados que el saldo: 'paid' y 'audited'
            # Estos son los ingresos reales que han entrado a la caja chica
            request_amount_ids = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', 'in', ['paid', 'audited'])
            ])
            amount = sum(line.request_amount for line in request_amount_ids)
            data.total_request_amount = amount
           

    def action_get_approve_request_amount(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            # Cambiar para mostrar solicitudes pagadas/auditadas (ingresos reales)
            total_approve_amount_ids = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', 'in', ['paid', 'audited'])
            ])
            return {
                'name': 'Ingresos Reales - Solicitudes Pagadas/Auditadas',
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
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form2').id
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
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form2').id
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
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form2').id
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
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_expense_form2').id
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

    # ============================================================================
    # MÉTODOS COMPUTADOS PARA NUEVOS ESTADOS DEL FLUJO DE CAJA CHICA
    # ============================================================================

    def compute_sent_state(self):
        for data in self:
            sent_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'sent')])
            data.sent_state = sent_ids

    def action_get_sent(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_sent_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'sent')])
            return {
                'name': 'Solicitudes Enviadas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_sent_ids.ids)]
            }

    def compute_received_state(self):
        for data in self:
            received_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'received')])
            data.received_state = received_ids

    def action_get_received(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_received_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'received')])
            return {
                'name': 'Solicitudes Recibidas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_received_ids.ids)]
            }

    def compute_paid_state(self):
        for data in self:
            paid_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'paid')])
            data.paid_state = paid_ids

    def action_get_paid(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_paid_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'paid')])
            return {
                'name': 'Solicitudes Pagadas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_paid_ids.ids)]
            }

    def compute_audited_state(self):
        for data in self:
            audited_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'audited')])
            data.audited_state = audited_ids

    def action_get_audited(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_audited_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'audited')])
            return {
                'name': 'Solicitudes Auditadas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_audited_ids.ids)]
            }

    def compute_rejected_state(self):
        for data in self:
            rejected_ids = self.env['petty.cash.request'].search_count(
                [('petty_journal_id', '=', data.id), ('state', '=', 'rejected')])
            data.rejected_state = rejected_ids

    def action_get_rejected(self):
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            total_rejected_ids = self.env['petty.cash.request'].search([('petty_journal_id', '=', data.id), ('state', '=', 'rejected')])
            return {
                'name': 'Solicitudes Rechazadas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', total_rejected_ids.ids)]
            }

    # ============================================================================
    # MÉTODO COMPUTADO PARA EL SALDO TOTAL DE CAJA CHICA
    # ============================================================================

    def compute_petty_cash_balance(self):
        """
        Calcula el saldo total de la caja chica.
        
        LÓGICA DE CÁLCULO:
        - INGRESOS: Solo solicitudes que han sido efectivamente pagadas ('paid') o auditadas ('audited')
          Estas representan el dinero que realmente ha entrado a la caja chica.
        - GASTOS: Solo gastos completados ('done')
          Estos representan el dinero que realmente ha salido de la caja chica.
        - SALDO = INGRESOS REALES - GASTOS REALES
        
        NOTA: Las solicitudes 'approved' NO se incluyen en ingresos porque aún no se ha 
        transferido el dinero físicamente a la caja chica.
        """
        for data in self:
            # Calcular ingresos REALES: solicitudes en estado 'paid' o 'audited'
            income_requests = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', 'in', ['paid', 'audited'])
            ])
            total_income = sum(request.request_amount for request in income_requests)
            
            # Calcular gastos REALES: gastos en estado 'done'
            expense_records = self.env['petty.cash.expense'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', '=', 'done')
            ])
            total_expenses = sum(expense.expense_amount for expense in expense_records)
            
            # Calcular saldo: Ingresos REALES - Gastos REALES
            data.petty_cash_balance = total_income - total_expenses

    def action_get_balance_detail(self):
        """
        Acción para mostrar el detalle del saldo de caja chica
        """
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            balance_requests = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', 'in', ['paid', 'audited'])
            ])
            return {
                'name': 'Detalle del Saldo - Solicitudes Pagadas/Auditadas',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', balance_requests.ids)]
            }

    def compute_pending_approved_amount(self):
        """
        Calcula el monto de solicitudes aprobadas pero aún no pagadas
        """
        for data in self:
            pending_requests = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', '=', 'approved')
            ])
            data.pending_approved_amount = sum(request.request_amount for request in pending_requests)

    def action_get_pending_approved_detail(self):
        """
        Acción para mostrar solicitudes aprobadas pendientes de pago
        """
        tree_id = self.env.ref('dev_petty_cash.view_petty_cash_request_tree').id
        form_id = self.env.ref('dev_petty_cash.view_petty_cash_request_form').id
        for data in self:
            pending_requests = self.env['petty.cash.request'].search([
                ('petty_journal_id', '=', data.id), 
                ('state', '=', 'approved')
            ])
            return {
                'name': 'Solicitudes Aprobadas Pendientes de Pago',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree, form',
                'res_model': 'petty.cash.request',
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current',
                'domain': [('id', 'in', pending_requests.ids)]
            }


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:





