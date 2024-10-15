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
from odoo.tools import float_round


class petty_cash_expense(models.Model):
    _name = 'petty.cash.expense'
    _description = 'Petty Cash expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    
    @api.model
    def _get_request_by(self):
        employee_id =self.env['hr.employee'].search([('user_id','=',self.env.user.id)])
        return employee_id.id or False
    
    name = fields.Char('Name', default='/', tracking=1)
    employee_id = fields.Many2one('hr.employee', string='Employee', default=_get_request_by, tracking=2)
    petty_journal_id = fields.Many2one('account.journal', string='Petty Cash Journal', tracking=2, domain="[('is_petty_cash', '=', True)]")
    payment_journal_id = fields.Many2one('account.journal', string='Payment Journal', domain="[('is_petty_cash', '=', False)]")
    date = fields.Date('Date', copy=False, default=fields.Datetime.now)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self:self.env.company.currency_id)
    user_id = fields.Many2one('res.users', string='User', default=lambda self:self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self:self.env.company)
    state = fields.Selection(string='State', selection=[('draft', 'Draft'),
                                                        ('confirm', 'Confirm'),
                                                        ('validate', 'Validate'),
                                                        ('done', 'Done'),
                                                        ('cancel','Cancel')], default='draft', tracking=4)
    expense_lines = fields.One2many('petty.expense.lines','expense_id', string='Expense Lines')
    payment_ids = fields.Many2many('account.payment', string='Payments', copy=False)
    balance = fields.Monetary(
    'Balance', 
    compute='saldo_caja_chica', 
    store=True, 
    help="El Balance es de la caja chica seleccionada y solicitudes con estado = Pagadas")   # se desarrollo nuestro propio calculador de saldo y se quito: '_get_balance'
    expense_amount = fields.Monetary('Expense Amount', compute='_get_expense_amount', tracking=3)
    request_ids = fields.Many2many('petty.cash.request', string='Requests')
    remaining_balance = fields.Monetary('Remaining Balance', compute='_get_expense_amount', store=True)
    note = fields.Text('Notes')
    payment_count = fields.Integer('Payment Count', compute='_count_payment')
    account_move_ids_expense = fields.One2many(
        'account.move',
        'petty_cash_expense_id',
        string='Asientos de Gastos de Caja Chica',
        readonly=True,
        copy=False
    )
    account_move_name = fields.Char(string="Account Move Name", compute="_compute_account_move_name")
    # Campo que totaliza todos los impuestos
    total_tax_amount = fields.Text(string='Total Tax Amount', compute='_compute_total_tax_amount_only')

    # Campo que almacena el desglose de impuestos en formato JSON (opcional)
    tax_breakdown_json = fields.Text(string='Tax Breakdown', compute='_compute_total_tax_amount', default='{}') 

    @api.depends('expense_lines.tax_amount')
    def _compute_total_tax_amount_only(self):
        for expense in self:
            # Usamos el método que devuelve un diccionario con los impuestos
            tax_totals = expense.expense_lines.get_total_tax_amount_by_tax()
            
            # Si el diccionario está vacío, asignamos 0 como valor predeterminado
            if tax_totals:
                # Redondeamos cada valor de impuesto a 2 decimales
                tax_totals = {tax: round(amount, 2) for tax, amount in tax_totals.items()}
                total_tax = round(sum(tax_totals.values()), 2)
            else:
                total_tax = 0.0
            
            # Asignamos el valor calculado al campo computado
            expense.total_tax_amount = total_tax
            
            # Para asegurar que el breakdown se inicializa
            expense.tax_breakdown_json = str(tax_totals) if tax_totals else '{}'
    
    @api.depends('expense_lines.tax_amount')
    def _compute_total_tax_amount(self):
        for expense in self:
            tax_totals = expense.expense_lines.get_total_tax_amount_by_tax()
            # Suma de los valores del diccionario
            total_tax = sum(tax_totals.values()) if tax_totals else 0.0
            # Almacenar el total de impuestos
            expense.total_tax_amount = total_tax

            # Convertir el diccionario en un formato JSON para mostrar o almacenar (opcional)
            expense.tax_breakdown_json = str(tax_totals) if tax_totals else '{}'

    @api.depends('account_move_ids_expense')
    def _compute_account_move_name(self):
        for record in self:
            if record.account_move_ids_expense:
                # Assuming it's One2many, we'll take the first name
                record.account_move_name = record.account_move_ids_expense[0].name
            else:
                record.account_move_name = 'Asiento de Diario'

    
    def action_view_payment(self):
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action['context']={}
        action['domain'] = [('id','in',self.payment_ids.ids)]
        return action
    
    @api.depends('payment_ids')
    def _count_payment(self):
        for expense in self:
            expense.payment_count = len(expense.payment_ids)
            
    @api.depends('expense_lines.amount', 'balance')
    def _get_expense_amount(self):
        for expense in self:
            amount = sum(line.amount for line in expense.expense_lines)
            expense.expense_amount = amount
            expense.remaining_balance = expense.balance - expense.expense_amount

    @api.depends('employee_id','petty_journal_id','currency_id')
    def _get_balance(self):
        for expense in self:
            request_ids = expense.env['petty.cash.request'].search([('request_by','=',expense.employee_id.id),
                                                                 ('petty_journal_id','=',expense.petty_journal_id.id),
                                                                 ('state','=','approve'),
                                                                 ('balance','>',0)])
            amount = 0
            for request in request_ids:
                if request.balance and request.balance > 0:
                    if request.currency_id.id != expense.currency_id.id:
                        currency_id = request.currency_id.with_context(date=request.date)
                        amount  += currency_id.compute(abs(request.balance), expense.currency_id)
                    else:
                        amount += abs(request.balance)
            expense.balance = amount
        
    
    def create_payment(self):
        account_ids = []
        for line in self.expense_lines:
            if line.account_id.id not in account_ids:
                account_ids.append(line.account_id.id)
                
        payment_ids= []
        for account in account_ids:
            amount = 0
            for line in self.expense_lines:
                if line.account_id.id == account:
                    amount += line.amount
            vals={
                'payment_type':'outbound',
                'partner_id':self.company_id.partner_id.id or False,
                'destination_account_id':self.petty_journal_id.default_account_id.id or False,
                'is_internal_transfer':True,
                'company_id':self.company_id and self.company_id.id or False,
                'amount':amount or 0.0,
                'currency_id':self.currency_id and self.currency_id.id or False,
                'journal_id':self.payment_journal_id and self.payment_journal_id.id or False,
                'destination_journal_id':self.petty_journal_id.id or False,
            }
            payment_id = self.env['account.payment'].sudo().create(vals)
            if payment_id:
                payment_id.action_post()
                payment_ids.append(payment_id.id)
        self.payment_ids = [(6,0, payment_ids)]
            
            
    def reconcile_payment(self):
        request_ids = self.env['petty.cash.request'].search([('request_by','=',self.employee_id.id),
                                                                 ('petty_journal_id','=',self.petty_journal_id.id),
                                                                 ('state','=','approve'),
                                                                 ('balance','>',0)])
        credit_move_lines = self.env['account.move.line']
        debit_move_lines = self.env['account.move.line']
        account_id = self.petty_journal_id.default_account_id
        for request in request_ids:
            if request.payment_id and request.payment_id.move_id:
                credit_line = request.payment_id.move_id.line_ids.filtered(lambda t: t.account_id.id == account_id.id)
                credit_res_amount = abs(credit_line.amount_residual_currency)
                if credit_res_amount:
                    credit_move_lines += credit_line
        for payment in self.payment_ids:
            if payment.move_id:
                d_line = payment.move_id.line_ids.filtered(lambda t: t.account_id.id == account_id.id)
                res_amount = abs(d_line.amount_residual_currency)
                if res_amount:
                    debit_move_lines += d_line
        
        if debit_move_lines and credit_move_lines:
            (credit_move_lines + debit_move_lines).reconcile()
        return True

    @api.depends('employee_id', 'petty_journal_id', 'expense_lines', 'expense_lines.amount', 'state')
    def saldo_caja_chica(self):
        for expense in self:
            expense.balance = expense.solicitudes_caja_chica_aprobadas() - expense.gastos_confirmados2()
        return expense.balance

    def solicitudes_caja_chica_aprobadas(self):
        sumatoria = 0
        for expense in self:
            # Se quito los dineros pedidos para los colaboradores('request_by','=',expense.employee_id.id),
            request_ids = expense.env['petty.cash.request'].search([('petty_journal_id','=',expense.petty_journal_id.id),
                                                                 ('state','=','paid'),
                                                                 ('balance','>',0)])
            for request in request_ids:
                sumatoria += request.request_amount
        return sumatoria
    
    def gastos_confirmados(self):
        sumatoria = 0
        for expense in self:
            if self.state == 'confirm':
                sumatoria += self.expense_amount
            else:
                sumatoria = sumatoria
        return sumatoria

    def gastos_confirmados2(self):
        max_expense_id = self.id
        petty_cash_id = self.petty_journal_id.id
        total = 0.0

        # Verifica que max_expense_id y petty_cash_id tengan valores válidos
        if max_expense_id and petty_cash_id:
            # Si ambos valores existen, buscar registros con id menor que max_expense_id
            expense_lines = self.search([('id', '<', max_expense_id), ('petty_journal_id', '=', petty_cash_id)])
            total = sum(line.expense_amount for line in expense_lines)
        else:
            # Si max_expense_id es un objeto y tiene un atributo 'origin', verifica su tipo
            if hasattr(max_expense_id, 'origin'):
                if isinstance(max_expense_id.origin, bool):
                    # Si el tipo es bool, buscar líneas con petty_journal_id
                    expense_lines = self.search([('petty_journal_id', '=', petty_cash_id)])
                    total = sum(line.expense_amount for line in expense_lines)
                elif isinstance(max_expense_id.origin, int):
                    # Si el tipo es int, buscar líneas con id menor que max_expense_id
                    expense_lines = self.search([('id', '<', max_expense_id.origin), ('petty_journal_id', '=', petty_cash_id)])
                    total = sum(line.expense_amount for line in expense_lines)

        return total


    def action_confirm(self):
        # Calculo del saldo de la caja chica
        if self.saldo_caja_chica() <= self.expense_amount:
            raise ValidationError(_("In Petty Cash have only %s balance")%(self.balance))
        self.state = 'confirm'
        
    def action_validate(self):
        account_ids = []
        for line in self.expense_lines:
            if line.account_id.id not in account_ids:
                account_ids.append(line.account_id.id)
                
        for account in account_ids:
            amount = 0
            for line in self.expense_lines:
                amount += line.amount
        vals={
            'payment_type':'outbound',
            'partner_id':self.company_id.partner_id.id or False,
            'destination_account_id':self.petty_journal_id.default_account_id.id or False,
            'is_internal_transfer':True,
            'company_id':self.company_id and self.company_id.id or False,
            'amount':amount or 0.0,
            'currency_id':self.currency_id and self.currency_id.id or False,
            'journal_id':self.payment_journal_id and self.payment_journal_id.id or False,
            'destination_journal_id':self.petty_journal_id.id or False,
            'name':self.name,
            'account_id_cr':self.petty_journal_id.default_account_id.id or False,
            'date':self.date,

        }
        expense_data = self.create_journals_entry(vals)
        print(expense_data)
        if expense_data:
            # Asiento de Diario GAstos de la Caja Chica
            invoice_id = self.env['account.move'].create(expense_data)
            invoice_id.action_post()
        else:
            raise UserError("Los datos del gasto de caja chica están vacios.")
        print(f"Asiento de Gastos de Caja Chica creada con ID: {invoice_id}")
        self.account_move_ids_expense = invoice_id
        # Agregar el nuevo asiento contable a la relación One2many
        self.account_move_ids_expense = [(4, invoice_id.id)]
        self.state = 'done'

    def create_journals_entry(self, vals):
        # ASIENTO DE DIARIO ORIGEN  DEBITO A LA CUENTA INTERNA DE TRANSFERENCIAS
        #                           CREDITO A LA CUENTA POR DEFAULT DEL DIARIO DE PAGO
        supplier_id = vals['partner_id']  # ID del proveedor

        # Línea de crédito (para el gasto total)
        invoice_lines = [
            {
                'name': 'Crédito del Asiento de Compras de Gastos en Caja Chica: ' + vals['name'],
                'quantity': 1,
                'price_unit': vals['amount'],
                'price_subtotal': vals['amount'],
                'price_total': vals['amount'],
                'account_id': vals['account_id_cr'],  # ID de la cuenta contable de crédito
                'debit': 0.00,
                'credit': vals['amount'],  # Crédito al total del gasto
                'balance': -1 * vals['amount'],
                'amount_currency': -1 * vals['amount'],
            }
        ]

        # Líneas de débito (para cada línea de gasto)
        for line in self.expense_lines:
            invoice_number = line.invoice_number
            account_dr = line.account_id.id
            product_id = line.product_id.id
            name_product = line.product_id.name or line.note_expense
            partner_id_expense = line.supplier_id.id
            partner_name = line.supplier_id.name or ''
            tax_amount = line.tax_amount
            amount_dr = line.amount - tax_amount
            analytic_distribution = self.convert_to_distribution(line.analytic_account_id)
            # Agregar línea de débito para el gasto
            invoice_lines.append({
                'name': 'Débito por: ' + name_product + ' # Fact.: ' + invoice_number + ' Prov.: ' + partner_name,
                'partner_id': partner_id_expense,
                'account_id': account_dr,  # ID de la cuenta contable de débito
                'debit': amount_dr,
                'credit': 0.00,
                'quantity': 1,
                'price_unit': amount_dr,
                'price_subtotal': amount_dr,
                'price_total': amount_dr,
                'product_id': product_id,
                'balance': amount_dr,
                'amount_currency': amount_dr,
                'amount_residual': amount_dr,
                'amount_residual_currency': amount_dr,
                'analytic_distribution': analytic_distribution
            })

            # Agregar líneas de débito para cada impuesto relacionado, solo si tiene cuenta válida
            for tax_line in line.invoice_tax_id.invoice_repartition_line_ids:
                tax = tax_line.account_id

                # Verificar que la línea de impuesto tenga una cuenta válida
                if not tax:
                    continue  # Saltar si no hay una cuenta asociada

                tax_name = tax.display_name if tax.display_name else 'N/A'
                
                invoice_lines.append({
                    'name': 'Débito Impuesto: ' + tax_name + ' # Fact.: ' + invoice_number + ' Prov.: ' + partner_name,
                    'account_id': tax.id,  # ID de la cuenta contable de débito
                    'debit': tax_amount,
                    'credit': 0.00,
                    'balance': tax_amount,
                    'amount_currency': tax_amount,
                    'amount_residual': tax_amount,
                    'amount_residual_currency': tax_amount,
                })

        # Datos del asiento contable (encabezado)
        invoice_data = {
            'move_type': 'entry',
            'journal_id': vals['destination_journal_id'],  # Diario contable
            'partner_id': supplier_id,
            'invoice_date': vals['date'],
            'date': vals['date'],
            'invoice_line_ids': [(0, 0, line) for line in invoice_lines],  # Las líneas creadas
            'currency_id': vals['currency_id'],  # Moneda
            'ref': vals['name'],   # Referencia del asiento
        }

        return invoice_data
   
    @api.model
    def convert_to_distribution(self, analytic_account_id):
        if analytic_account_id:
            # Retornar un diccionario con el ID de la cuenta analítica y el 100% de distribución
            return {str(analytic_account_id.id): 100.0}
        else:
            return {}
    
    def action_create_payment(self):
        self.create_payment()
        self.state = 'payment'
        
    def action_reconcile(self):
        self.reconcile_payment()
        self.state = 'done'
        
    def action_cancel(self):
        self.state = 'cancel'
        
    def action_draft(self):
        self.state = 'draft'
        
    def unlink(self):
        for request in self:
            if request.state != 'draft':
                raise ValidationError(_("You can delete expense in draft state only."))
        return super(petty_cash_expense, self).unlink()
        
    @api.model
    def create(self, vals):
        vals.update({
            'name': self.env['ir.sequence'].next_by_code('petty.cash.expense') or '/',
			
        })
        return super(petty_cash_expense, self).create(vals)

class petty_expense_lines(models.Model):
    _name ='petty.expense.lines'
    _description = 'Petty Expense Lines'
    
    product_id = fields.Many2one('product.product', string='Particulars')
    account_id = fields.Many2one('account.account', string='Account')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    invoice_amount = fields.Monetary('Invoice Amount')
    amount = fields.Monetary('Amount')
    currency_id = fields.Many2one('res.currency', string='Currency')
    expense_id = fields.Many2one('petty.cash.expense', string='Expense', ondelete='cascade')
    # Campo relacionado que trae el estado desde el modelo padre
    expense_state = fields.Selection(related='expense_id.state', string='Expense State', store=True)
    # 
    date_expense = fields.Date('Date Expense', copy=False, default=fields.Datetime.now)
    invoice_number = fields.Char('Invoice No.', default='', tracking=1)
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain="[('supplier_rank', '>', 0)]", help="Select the supplier for this expense line")
    tax_amount = fields.Monetary('Tax Amount')
    invoice_tax_id = fields.Many2one(comodel_name='account.tax.template', help="The tax set to apply this distribution on invoices. Mutually exclusive with refund_tax_id")
    note_expense = fields.Char('Note Expense', default='Gasto para: ', tracking=1)

    def open_line_form(self):
        """
        Este método abrirá el formulario de la línea seleccionada en modo de edición.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Expense Line',
            'res_model': 'petty.expense.lines',
            'view_mode': 'form',
            'res_id': self.id,  # Asegúrate de pasar el id correcto de la línea.
            'target': 'new',  # Para abrirlo como un modal
        }
    
    @api.onchange('product_id')
    def onchange_product(self):
        self.ensure_one()
        self = self.with_company(self.expense_id.company_id)
        if self.product_id:
            accounts = self.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=False)
            account_id = accounts['expense'] or False
            self.account_id = account_id and account_id.id or False
            self.invoice_amount = self.product_id.standard_price or 0.0
    
    @api.onchange('invoice_tax_id')
    def _onchange_invoice_tax_id(self):
        if self.invoice_tax_id:
            if self.invoice_tax_id.amount_type == 'percent':  # Corregir el operador de comparación
                # Calcular el impuesto basado en el porcentaje
                self.tax_amount = (self.invoice_tax_id.amount / 100.0) * self.invoice_amount
            else:
                # Si el impuesto no es de tipo porcentaje, poner el valor en 0 (puedes ajustar según el tipo)
                self.tax_amount = 0.0
        else:
            # Si no hay impuesto seleccionado, el valor del impuesto es 0
            self.tax_amount = 0.0

    @api.onchange('tax_amount')
    def _onchange_tax_amount(self):
        if self.tax_amount:
            self.amount = self.invoice_amount + self.tax_amount

    @api.onchange('invoice_amount')
    def _onchange_invoice_amount(self):
        if self.invoice_amount:
            self.amount = self.invoice_amount + self.tax_amount

    def get_total_tax_amount_by_tax(self):
        tax_totals = {}
        for line in self:
            tax = line.invoice_tax_id
            if tax:
                if tax not in tax_totals:
                    tax_totals[tax] = 0.0
                tax_totals[tax] += line.tax_amount

        # Ahora tenemos un diccionario con el total de tax_amount para cada tax
        return tax_totals

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
class AccountMove(models.Model):
    _inherit = 'account.move'

    petty_cash_expense_id = fields.Many2one(
        'petty.cash.expense',
        string='Petty Cash Expense',
        ondelete='cascade'
    )
