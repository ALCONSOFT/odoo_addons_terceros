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
import logging


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
    help="Saldo disponible en caja chica = Ingresos reales (solicitudes paid/audited) - Gastos completados (done)")   # Lógica corregida para consistencia con dashboard
    expense_amount = fields.Monetary('Expense Amount', compute='_get_expense_amount', tracking=3)
    request_ids = fields.Many2many('petty.cash.request', string='Requests')
    remaining_balance = fields.Monetary('Remaining Balance', compute='_get_expense_amount', store=True)
    note = fields.Text('Notes')
    payment_count = fields.Integer('Payment Count', compute='_count_payment')
    preview_count = fields.Integer('Preview Count', compute='_count_preview')
    account_move_ids_expense = fields.One2many(
        'account.move',
        'petty_cash_expense_id',
        string='Asientos de Gastos de Caja Chica',
        readonly=True,
        copy=False
    )
    # Campo para enlazar asientos de vista previa
    preview_move_ids = fields.One2many(
        'account.move',
        'petty_cash_expense_preview_id',
        string='Asientos de Vista Previa',
        readonly=True,
        copy=False,
        help='Asientos temporales creados para vista previa'
    )
    account_move_name = fields.Char(string="Account Move Name", compute="_compute_account_move_name")
    # Campo que totaliza todos los impuestos
    total_tax_amount = fields.Text(string='Total Tax Amount', compute='_compute_total_tax_amount_only')

    # Campo que almacena el desglose de impuestos en formato JSON (opcional)
    tax_breakdown_json = fields.Text(string='Tax Breakdown', compute='_compute_total_tax_amount', default='{}') 

    @api.depends('expense_lines.product_lines.tax_amount')
    def _compute_total_tax_amount_only(self):
        for expense in self:
            # Calculamos el total de impuestos desde las líneas de producto
            total_tax = 0.0
            for line in expense.expense_lines:
                for product_line in line.product_lines:
                    total_tax += product_line.tax_amount
            
            expense.total_tax_amount = round(total_tax, 2)
    
    @api.depends('expense_lines.product_lines.tax_amount')
    def _compute_total_tax_amount(self):
        for expense in self:
            # Calculamos el desglose de impuestos por tipo desde las líneas de producto
            tax_totals = {}
            for line in expense.expense_lines:
                for product_line in line.product_lines:
                    if product_line.tax_id and product_line.tax_amount > 0:
                        tax_name = product_line.tax_id.name
                        if tax_name not in tax_totals:
                            tax_totals[tax_name] = 0.0
                        tax_totals[tax_name] += product_line.tax_amount
            
            # Suma total de impuestos
            total_tax = sum(tax_totals.values()) if tax_totals else 0.0
            expense.total_tax_amount = round(total_tax, 2)
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
    
    def action_view_preview_moves(self):
        """
        Muestra los asientos de vista previa enlazados a este gasto.
        """
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_journal_line")
        action['context'] = {}
        action['domain'] = [('id', 'in', self.preview_move_ids.ids)]
        action['name'] = _('Asientos de Vista Previa - %s') % self.name
        return action
    
    @api.depends('payment_ids')
    def _count_payment(self):
        for expense in self:
            expense.payment_count = len(expense.payment_ids)
    
    @api.depends('preview_move_ids')
    def _count_preview(self):
        for expense in self:
            expense.preview_count = len(expense.preview_move_ids.filtered(lambda m: m.state == 'draft'))
            
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
        """
        Calcula el saldo de la caja chica de forma consistente con el dashboard.
        
        LÓGICA CORREGIDA:
        - INGRESOS: Solicitudes en estado 'paid' o 'audited' (dinero real en caja)
        - GASTOS: Gastos en estado 'done' (dinero realmente gastado)
        - SALDO = INGRESOS REALES - GASTOS REALES
        
        NOTA: Solo se consideran gastos completados ('done'), no gastos en borrador o confirmados.
        """
        for expense in self:
            ingresos_reales = expense.solicitudes_caja_chica_pagadas_auditadas()
            gastos_reales = expense.gastos_completados_caja_chica()
            expense.balance = ingresos_reales - gastos_reales
        return expense.balance

    def solicitudes_caja_chica_pagadas_auditadas(self):
        """
        Calcula el total de ingresos reales a la caja chica.
        Solo considera solicitudes que han sido efectivamente pagadas o auditadas.
        """
        total_ingresos = 0.0
        for expense in self:
            if expense.petty_journal_id:
                # Buscar solicitudes pagadas y auditadas para esta caja chica
                request_ids = expense.env['petty.cash.request'].search([
                    ('petty_journal_id', '=', expense.petty_journal_id.id),
                    ('state', 'in', ['paid', 'audited'])
                ])
                total_ingresos = sum(request.request_amount for request in request_ids)
        return total_ingresos
    
    def gastos_completados_caja_chica(self):
        """
        Calcula el total de gastos realmente completados de esta caja chica.
        Solo considera gastos en estado 'done' (completados).
        """
        total_gastos = 0.0
        for expense in self:
            if expense.petty_journal_id:
                # Buscar todos los gastos completados de esta caja chica
                expense_records = expense.env['petty.cash.expense'].search([
                    ('petty_journal_id', '=', expense.petty_journal_id.id),
                    ('state', '=', 'done')
                ])
                total_gastos = sum(exp.expense_amount for exp in expense_records)
        return total_gastos

    def gastos_confirmados(self):
        """
        MÉTODO OBSOLETO - Mantener por compatibilidad pero no usar
        """
        sumatoria = 0
        for expense in self:
            if self.state == 'confirm':
                sumatoria += self.expense_amount
            else:
                sumatoria = sumatoria
        return sumatoria

    def gastos_confirmados2(self):
        """
        MÉTODO OBSOLETO - Reemplazado por gastos_completados_caja_chica()
        Mantener por compatibilidad pero usar el nuevo método
        """
        return self.gastos_completados_caja_chica()


    def action_confirm(self):
        # Calculo del saldo de la caja chica
        if self.saldo_caja_chica() <= self.expense_amount:
            raise ValidationError(_("In Petty Cash have only %s balance")%(self.balance))
        self.state = 'confirm'
        
    def action_validate_old(self):
        _logger = logging.getLogger(__name__) # Optional: for logging

        for expense_line in self.expense_lines:
            for product_line in expense_line.product_lines:
                product = product_line.product_id
                # Check only for stockable products
                if product.type == 'product':
                    _logger.debug(f"Checking stockable product: {product.display_name} on invoice {expense_line.invoice_number or 'N/A'}")

                    if not product_line.stock_move_line_id:
                        err_msg = _("Inventory justification missing for stockable product: {product_name} (Invoice: {invoice_num}, Line Note: {line_note}). "
                                    "A corresponding inventory entry record is required. No such stock move found.").format(
                                        product_name=product.display_name,
                                        invoice_num=expense_line.invoice_number or _('N/A'),
                                        line_note=expense_line.note_expense or _('N/A')
                                    )
                        raise ValidationError(err_msg)
                    _logger.debug(f"Found matching stock move: {product_line.stock_move_line_id} for product {product.display_name}")

        account_ids = []
        for line in self.expense_lines:
            for product_line in line.product_lines:
                if product_line.account_id and product_line.account_id.id not in account_ids:
                    account_ids.append(product_line.account_id.id)
        amount = 0        
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

    def action_preview_journal_entries(self):
        """
        Genera una vista previa de los asientos contables que se crearán al validar.
        Permite al contador revisar los asientos antes de confirmarlos.
        MEJORA: Evita duplicados y enlaza asientos con el gasto.
        """
        self.ensure_one()
        
        # Validar que hay líneas de gasto
        if not self.expense_lines:
            raise ValidationError(_("No hay líneas de gasto para generar asientos contables."))
        
        # Verificar si ya existe un asiento de vista previa para este gasto
        existing_preview = self.preview_move_ids.filtered(lambda m: m.state == 'draft')
        if existing_preview:
            # Si ya existe, mostrar el existente en lugar de crear uno nuevo
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vista Previa - Asientos Contables (Existente)'),
                'res_model': 'account.move',
                'res_id': existing_preview[0].id,
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_move_type': 'entry',
                    'is_preview': True,
                    'preview_expense_id': self.id,
                },
            }
        
        # Validar cuentas analíticas (misma validación que en action_validate)
        for line in self.expense_lines:
            for product_line in line.product_lines:
                if not product_line.account_analytic_id:
                    raise ValidationError(_(
                        "Falta cuenta analítica para:\n"
                        "Factura: %s\n"
                        "Proveedor: %s\n"
                        "Producto: %s"
                    ) % (
                        line.invoice_number or 'N/A',
                        line.supplier_id.name or 'N/A', 
                        product_line.product_id.display_name
                    ))
        
        # Generar las líneas de débito (misma lógica que action_validate)
        debit_lines = self._build_debit_lines()
        total = sum(l['debit'] for l in debit_lines)
        
        # Línea de crédito
        credit_line = {
            'name': _("Credito Petty Cash %s") % self.name,
            'account_id': self.petty_journal_id.default_account_id.id,
            'debit': 0.0,
            'credit': total,
        }
        
        # Crear asiento temporal (borrador) para vista previa
        move_vals = {
            'move_type': 'entry',
            'journal_id': self.petty_journal_id.id,
            'date': self.date,
            'ref': _("VISTA PREVIA - %s") % self.name,
            'state': 'draft',  # Mantener en borrador
            'petty_cash_expense_preview_id': self.id,  # ENLACE DIRECTO AL GASTO
            'line_ids': [
                (0, 0, x) for x in (debit_lines + [credit_line])
            ],
        }
        
        # Crear el asiento temporal enlazado
        preview_move = self.env['account.move'].create(move_vals)
        
        # Retornar acción para mostrar el asiento en una ventana modal
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vista Previa - Asientos Contables'),
            'res_model': 'account.move',
            'res_id': preview_move.id,
            'view_mode': 'form',
            'target': 'new',  # Abrir en modal
            'context': {
                'default_move_type': 'entry',
                'is_preview': True,  # Flag para identificar que es vista previa
                'preview_expense_id': self.id,  # Referencia al gasto
            },
        }

    def action_clean_preview_entries(self):
        """
        Limpia los asientos de vista previa creados para este gasto.
        Se ejecuta automáticamente al validar o cancelar.
        MEJORA: Usa relación directa para mayor eficiencia.
        """
        # Usar la relación directa en lugar de búsqueda por referencia
        preview_moves = self.preview_move_ids.filtered(lambda m: m.state == 'draft')
        if preview_moves:
            preview_moves.unlink()
        return True
    
    def action_clean_all_preview_entries(self):
        """
        Método adicional para limpiar TODOS los asientos de vista previa huérfanos.
        Útil para mantenimiento del sistema.
        """
        # Buscar asientos huérfanos (sin enlace o con enlace a gastos inexistentes)
        orphan_moves = self.env['account.move'].search([
            ('ref', 'ilike', 'VISTA PREVIA'),
            ('state', '=', 'draft'),
            '|',
            ('petty_cash_expense_preview_id', '=', False),
            ('petty_cash_expense_preview_id.state', 'in', ['done', 'cancel'])
        ])
        if orphan_moves:
            orphan_moves.unlink()
        return len(orphan_moves)

    # >>> NUEVO MÉTODO PARA VALIDAR LOS GASTOS DE CAJA CHICA
    def action_validate(self):
        for expense in self:
            # Limpiar asientos de vista previa antes de validar
            expense.action_clean_preview_entries()
            
            # Validar cuentas analíticas en cada línea de producto
            for line in expense.expense_lines:
                for product_line in line.product_lines:
                    if not product_line.account_analytic_id:
                        raise ValidationError(_(
                            "Falta cuenta analítica para:\n"
                            "Factura: %s\n"
                            "Proveedor: %s\n"
                            "Producto: %s"
                        ) % (
                            line.invoice_number or 'N/A',
                            line.supplier_id.name or 'N/A', 
                            product_line.product_id.display_name
                        ))
        for expense in self:
            # … tus validaciones previas …
            # 1. Recolectar líneas de débito
            debit_lines = expense._build_debit_lines()
            # 2. Calcular total y línea de crédito
            total = sum(l['debit'] for l in debit_lines)
            credit_line = {
                'name': _("Crédito Petty Cash %s") % expense.name,
                'account_id': expense.petty_journal_id.default_account_id.id,
                'debit': 0.0,
                'credit': total,
            }
            # 3. Crear asiento
            move_vals = {
                'move_type': 'entry',
                'journal_id': expense.petty_journal_id.id,
                'date': expense.date,
                'ref': expense.name,
                'invoice_line_ids': [
                    (0, 0, x) for x in (debit_lines + [credit_line])
                ],
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            expense.account_move_ids_expense = [(4, move.id)]
            expense.state = 'done'
    
    def _build_debit_lines(self):
        lines = []
        for line in self.expense_lines:
            for prod in line.product_lines:
                # Cuenta de gasto según producto/categoría
                account_dr = prod.product_id.property_account_expense_id.id \
                            or prod.product_id.categ_id.property_account_expense_categ_id.id
                lines.append({
                    'name': prod.product_id.display_name,
                    'account_id': account_dr,
                    'debit': prod.price_subtotal,
                    'credit': 0.0,
                    'analytic_distribution': { str(prod.account_analytic_id.id): 100.0 },
                })
                # Impuestos
                if prod.tax_amount:
                    tax_accts = prod.tax_id.invoice_repartition_line_ids\
                                    .filtered(lambda l: l.repartition_type=='tax')\
                                    .mapped('account_id')
                    if tax_accts:
                        lines.append({
                            'name': f"Impuesto {prod.tax_id.name}",
                            'account_id': tax_accts[0].id,
                            'debit': prod.tax_amount,
                            'credit': 0.0,
                        })
        return lines
    
    
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

        # Líneas de débito (para cada línea de producto en cada línea de gasto)
        for line in self.expense_lines:
            invoice_number = line.invoice_number
            partner_id_expense = line.supplier_id.id
            partner_name = line.supplier_id.name or ''
            
            # Procesar cada línea de producto
            for product_line in line.product_lines:
                if not product_line.account_id:
                    continue  # Saltar si no hay cuenta contable
                    
                account_dr = product_line.account_id.id
                product_id = product_line.product_id.id
                name_product = product_line.product_id.name or line.note_expense
                tax_amount = product_line.tax_amount
                amount_dr = product_line.price_subtotal  # Solo el subtotal sin impuesto
                analytic_distribution = self.convert_to_distribution(product_line.account_analytic_id)
                
                # Agregar línea de débito para el gasto del producto
                invoice_lines.append({
                    'name': 'Débito por: ' + name_product + ' # Fact.: ' + invoice_number + ' Prov.: ' + partner_name,
                    'partner_id': partner_id_expense,
                    'account_id': account_dr,  # ID de la cuenta contable de débito
                    'debit': amount_dr,
                    'credit': 0.00,
                    'quantity': product_line.quantity,
                    'price_unit': product_line.price_unit,
                    'price_subtotal': amount_dr,
                    'price_total': amount_dr,
                    'product_id': product_id,
                    'balance': amount_dr,
                    'amount_currency': amount_dr,
                    'amount_residual': amount_dr,
                    'amount_residual_currency': amount_dr,
                    'analytic_distribution': analytic_distribution
                })
                
                # Agregar línea de débito para el impuesto del producto, si existe
                if product_line.tax_id and tax_amount > 0:
                    for tax_line in product_line.tax_id.invoice_repartition_line_ids:
                        tax_account = tax_line.account_id
                        
                        # Verificar que la línea de impuesto tenga una cuenta válida
                        if not tax_account:
                            continue  # Saltar si no hay una cuenta asociada
                        
                        tax_name = tax_account.display_name if tax_account.display_name else 'N/A'
                        
                        invoice_lines.append({
                            'name': 'Débito Impuesto: ' + tax_name + ' # Fact.: ' + invoice_number + ' Prov.: ' + partner_name,
                            'account_id': tax_account.id,  # ID de la cuenta contable de débito
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
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_expense desc, id desc'
    
    # product_id = fields.Many2one('product.product', string='Particulars')
    product_lines = fields.One2many('petty.expense.line.product', 'expense_line_id', string='Product Lines')
    # account_id = fields.Many2one('account.account', string='Account')
    # analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    invoice_amount = fields.Monetary('Invoice Amount', compute='_compute_invoice_amount', store=True, tracking=True)
    amount = fields.Monetary('Amount', compute='_compute_amount', store=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency')
    expense_id = fields.Many2one('petty.cash.expense', string='Expense', ondelete='cascade')
    # Campo relacionado que trae el estado desde el modelo padre
    expense_state = fields.Selection(related='expense_id.state', string='Expense State', store=True)
    # 
    date_expense = fields.Date('Date Expense', copy=False, default=fields.Datetime.now, tracking=True)
    invoice_number = fields.Char('Invoice No.', default='', tracking=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain="[('supplier_rank', '>', 0)]", help="Select the supplier for this expense line", tracking=True)
    tax_amount = fields.Monetary('Tax Amount', compute='_compute_tax_amount', store=True, tracking=True)
    invoice_tax_id = fields.Many2one(comodel_name='account.tax.template', help="The tax set to apply this distribution on invoices. Mutually exclusive with refund_tax_id", tracking=True)
    note_expense = fields.Char('Note Expense', default='Gasto para: ', tracking=True)
    
    # Campo para anexos de documentos (facturas, recibos, etc.)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'petty_expense_line_attachment_rel',
        'expense_line_id',
        'attachment_id',
        string='Documentos Adjuntos',
        help='Facturas, recibos y otros documentos relacionados con esta línea de gasto'
    )
    
    # Campo computado para mostrar el número de documentos adjuntos
    attachment_count = fields.Integer('Número de Documentos', compute='_compute_attachment_count')
    
    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for line in self:
            line.attachment_count = len(line.attachment_ids)

    @api.depends('product_lines.price_subtotal')
    def _compute_invoice_amount(self):
        for line in self:
            line.invoice_amount = sum(p_line.price_subtotal for p_line in line.product_lines)

    @api.depends('product_lines.tax_amount')
    def _compute_tax_amount(self):
        """
        Calcula el total de impuestos desde las líneas de producto
        """
        for line in self:
            line.tax_amount = sum(p_line.tax_amount for p_line in line.product_lines)

    @api.depends('invoice_amount', 'tax_amount', 'product_lines.price_subtotal', 'product_lines.tax_amount')
    def _compute_amount(self):
        for line in self:
            line.amount = line.invoice_amount + line.tax_amount

    def recalculate_totals(self):
        """
        Método para recalcular todos los totales de la línea de gasto
        Se ejecuta automáticamente cuando cambian las líneas de producto
        """
        self.ensure_one()
        
        # Forzar recálculo de campos computados
        self._compute_invoice_amount()
        self._compute_tax_amount()
        self._compute_amount()
        
        # Guardar automáticamente los cambios
        if self.id:
            # Solo guardar si el registro ya existe en la base de datos
            self.env.cr.commit()
        
        # Recalcular también los totales del gasto padre
        if self.expense_id:
            self.expense_id._compute_total_tax_amount_only()
            self.expense_id._compute_total_tax_amount()
            self.expense_id._get_expense_amount()

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
    
    def action_view_attachments(self):
        """
        Método para abrir la vista de documentos adjuntos de esta línea de gasto.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Documentos Adjuntos',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': 'petty.expense.lines',
                'default_res_id': self.id,
            },
            'target': 'current',
        }
    
    def message_post_expense_line_created(self):
        """
        Envía un mensaje automático cuando se crea una nueva línea de gasto.
        """
        self.message_post(
            body=f"Nueva línea de gasto creada para el proveedor {self.supplier_id.name or 'N/A'} "
                 f"con factura #{self.invoice_number or 'N/A'} por un monto de {self.amount} {self.currency_id.name or ''}",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
    
    def message_post_amount_changed(self, old_amount, new_amount):
        """
        Envía un mensaje cuando cambia el monto de la línea de gasto.
        """
        self.message_post(
            body=f"Monto actualizado de {old_amount} a {new_amount} {self.currency_id.name or ''}",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
    
    @api.model
    def create(self, vals):
        """
        Override create para enviar mensaje automático al crear línea.
        """
        line = super(petty_expense_lines, self).create(vals)
        line.message_post_expense_line_created()
        return line
    
    # @api.onchange('product_id')
    # def onchange_product(self):
    #     self.ensure_one()
    #     self = self.with_company(self.expense_id.company_id)
    #     if self.product_id:
    #         accounts = self.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=False)
    #         account_id = accounts['expense'] or False
    #         self.account_id = account_id and account_id.id or False
    #         self.invoice_amount = self.product_id.standard_price or 0.0
    
    @api.onchange('invoice_tax_id', 'invoice_amount')
    def _onchange_invoice_tax_id(self):
        if self.invoice_tax_id:
            if self.invoice_tax_id.amount_type == 'percent':  # Corregir el operador de comparación
                # Calcular el impuesto basado en el porcentaje
                self.tax_amount = (self.invoice_tax_id.amount / 100.0) * self.invoice_amount
            else:
                # Si el impuesto no es de tipo porcentaje, poner el valor en 0 (puedes ajustar según el tipo)
                self.tax_amount = 0.0 # Or handle fixed amounts if necessary
        else:
            # Si no hay impuesto seleccionado, el valor del impuesto es 0
            self.tax_amount = 0.0

    # @api.onchange('tax_amount')
    # def _onchange_tax_amount(self):
    #     if self.tax_amount:
    #         self.amount = self.invoice_amount + self.tax_amount

    # @api.onchange('invoice_amount')
    # def _onchange_invoice_amount(self):
    #     if self.invoice_amount:
    #         self.amount = self.invoice_amount + self.tax_amount

    def get_total_tax_amount_by_tax(self):
        tax_totals = {}
        for line in self:
            # Ahora obtenemos los impuestos desde las líneas de producto
            for product_line in line.product_lines:
                tax = product_line.tax_id
                if tax and product_line.tax_amount > 0:
                    if tax not in tax_totals:
                        tax_totals[tax] = 0.0
                    tax_totals[tax] += product_line.tax_amount

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
    # Campo para enlazar asientos de vista previa
    petty_cash_expense_preview_id = fields.Many2one(
        'petty.cash.expense',
        string='Petty Cash Expense Preview',
        ondelete='cascade',
        help='Enlace a gasto de caja chica para asientos de vista previa'
    )

# PARCHES PROPUESTOS PARA ENLAZAR LA ENTRADA DE INVENTARIO A CADA PRODUCTO ALMACENABLE
# Archivo original: petty_cash_expense.py 
# Inserta/actualiza las siguientes secciones en tu archivo.

# -----------------------------------------------------------------------------
# 1) NUEVO CAMPO EN petty.expense.line.product
# -----------------------------------------------------------------------------
# Ubica la definición de la clase `petty_expense_line_product` y agrega el campo
# `stock_move_line_id` justo después de `inventory_justification_ref`.

class petty_expense_line_product(models.Model):
    _name = 'petty.expense.line.product'
    _inherit = 'purchase.order.line'
    _description = 'Petty Expense Line Product'

    expense_line_id = fields.Many2one('petty.expense.lines', string='Expense Line', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float('Quantity', default=1.0)
    price_unit = fields.Float('Unit Price')
    price_subtotal = fields.Monetary('Subtotal', compute='_compute_subtotal', store=True, tracking=True)
    currency_id = fields.Many2one(related='expense_line_id.currency_id', store=True)
    # inventory_justification_ref = fields.Char('Inventory Justification Ref')
    # Impuesto, Fase, Vehiculo
    tax_id = fields.Many2one('account.tax', string='Tax', 
                             domain="[('type_tax_use', '=', 'purchase')]",
                             help='Impuesto de compra aplicable a este producto')
    tax_amount = fields.Monetary('Tax Amount', compute='_compute_tax_amount', store=True, tracking=True)
    price_total = fields.Monetary('Total', compute='_compute_price_total', store=True, tracking=True)
    account_id = fields.Many2one('account.account', string='Account', required=True, 
                                 help='Cuenta contable para este producto')
    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        readonly=False, string='Cuenta Analítica')

    phase_id = fields.Many2one("project.phaseproject",
                               string="Fase",
                               tracking=True,
                               )

    vehiculo_id = fields.Many2one('fleet.vehicle', string='Vehículo')

    # >>> NUEVO ENLACE A LA LÍNEA DE MOVIMIENTO DE ENTRADA DE INVENTARIO
    stock_move_line_id = fields.Many2one(
        'stock.move.line',
        string='Entrada de Inventario',
        domain="[('state', '=', 'done'), ('picking_id.picking_type_id.code', '=', 'incoming'), ('product_id', '=', product_id)]",
        help='Selecciona la línea de movimiento que evidencia la entrada en inventario. Solo requerido para productos tipo almacenable.'
    )

    is_credit_note_line = fields.Boolean('Is Credit Note Line', default=False)

    @api.depends('quantity', 'price_unit','tax_id')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.depends('price_subtotal', 'tax_id')
    def _compute_tax_amount(self):
        self._compute_subtotal()
        """
        Calcula el monto del impuesto basado en el subtotal y el impuesto seleccionado
        """
        for line in self:
            if line.tax_id and line.price_subtotal:
                if line.tax_id.amount_type == 'percent':
                    line.tax_amount = (line.tax_id.amount / 100.0) * line.price_subtotal
                elif line.tax_id.amount_type == 'fixed':
                    line.tax_amount = line.tax_id.amount * line.quantity
                else:
                    line.tax_amount = 0.0
            else:
                line.tax_amount = 0.0

    @api.depends('price_subtotal', 'tax_amount')
    def _compute_price_total(self):
        """
        Calcula el precio total (subtotal + impuesto)
        """
        for line in self:
            line.price_total = line.price_subtotal + line.tax_amount

    @api.onchange('quantity', 'price_unit', 'tax_id')
    def _onchange_recalculate_totals(self):
        """
        Recalcula automáticamente los totales cuando cambian cantidad, precio unitario o impuesto
        """
        # Los campos computados se actualizarán automáticamente
        # Pero también activamos el recálculo en la línea padre
        if self.expense_line_id:
            # Usar call_soon para evitar problemas de recursión
            self.env.context = dict(self.env.context, recalculate_totals=True)

    @api.model
    def create(self, vals):
        """
        Override create para recalcular totales automáticamente
        """
        line = super(petty_expense_line_product, self).create(vals)
        if line.expense_line_id:
            line.expense_line_id.recalculate_totals()
        return line

    def write(self, vals):
        """
        Override write para recalcular totales automáticamente cuando se modifica
        """
        # Campos que requieren recálculo
        recalc_fields = ['quantity', 'price_unit', 'tax_id']
        needs_recalc = any(field in vals for field in recalc_fields)
        
        result = super(petty_expense_line_product, self).write(vals)
        
        if needs_recalc:
            for line in self:
                if line.expense_line_id:
                    line.expense_line_id.recalculate_totals()
        
        return result

    def unlink(self):
        """
        Override unlink para recalcular totales cuando se elimina una línea
        """
        expense_lines = self.mapped('expense_line_id')
        result = super(petty_expense_line_product, self).unlink()
        
        # Recalcular totales de las líneas padre después de eliminar
        for expense_line in expense_lines:
            if expense_line.exists():
                expense_line.recalculate_totals()
        
        return result

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Cada producto maneja su propia cuenta analítica independientemente
            # No necesitamos heredar de la línea padre
            return {
                'domain': {
                    'stock_move_line_id': [
                        ('product_id', '=', self.product_id.id),
                        ('state', '=', 'done'),
                        ('picking_id.picking_type_id.code', '=', 'incoming'),
                    ]
                }
            }
        else:
            return {
                'domain': {
                    'stock_move_line_id': [
                        ('state', '=', 'done'),
                        ('picking_id.picking_type_id.code', '=', 'incoming'),
                    ]
                }
            }

    # ---------------------------------------------------------------------
    # CONSTRAINT PARA OBLIGAR EL ENLACE EN PRODUCTOS ALMACENABLES
    # ---------------------------------------------------------------------
    @api.constrains('product_id', 'stock_move_line_id')
    def _check_stock_move_required(self):
        for rec in self:
            if rec.product_id and rec.product_id.type == 'product' and not rec.stock_move_line_id:
                raise ValidationError(_('El campo "Inventory Entry" es obligatorio para productos almacenables (%s).') % rec.product_id.display_name)

    # ---------------------------------------------------------------------
    # NO OLVIDES importar ValidationError al inicio del archivo si no existe:
    # from odoo.exceptions import ValidationError
    # ---------------------------------------------------------------------
