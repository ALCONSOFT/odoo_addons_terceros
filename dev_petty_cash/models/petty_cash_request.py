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
    note = fields.Text('Notes', tracking=1)
    request_to = fields.Many2one('hr.employee', string='Request To', tracking=1)
    request_by = fields.Many2one('hr.employee', string='Request By', default=_get_request_by, tracking=1)
    # Quitando dominio para cajas menudas: domain="[('is_petty_cash', '=', True)]"
    payment_journal_id = fields.Many2one('account.journal', string='Payment Journal', domain="[('type', 'in', ['bank', 'cash']), ('is_petty_cash', '!=', True)]",tracking=1)
    petty_journal_id=  fields.Many2one('account.journal', string='Petty Cash Journal', domain="[('is_petty_cash', '=', True)]", tracking=2)
    date = fields.Date('Date', copy=False, default=fields.Datetime.now)
    request_amount = fields.Monetary('Request Amount', tracking=2)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self:self.env.company.currency_id)
    user_id = fields.Many2one('res.users', string='User', default=lambda self:self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self:self.env.company)
    state = fields.Selection(string='State', selection=[('draft', 'Draft'),
                                                        ('request', 'Requested'),
                                                        ('approve', 'Approved'),
                                                        ('audited', 'Audited'),
                                                        ('paid', 'Paid'),
                                                        ('cancel','Cancel'),
                                                        ('reject','Reject')], default='draft', tracking=4)
    payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
    balance = fields.Monetary('Balance', compute='_get_balance')
    account_move_ids_send = fields.One2many(
        'account.move',
        'petty_cash_request_id_send',
        string='Asientos de Envío',
        readonly=True,
        copy=False,
        tracking=1
    )
    account_move_ids_receive = fields.One2many(
        'account.move',
        'petty_cash_request_id_receive',
        string='Asientos de Recepción',
        readonly=True,
        copy=False,
        tracking=1
    )
    request_type = fields.Selection([
        ('apertura', 'Apertura'),
        ('reembolso', 'Reembolso')
    ], string="Tipo de Solicitud", default='reembolso', required=True, tracking=1
    )
    pay_method = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('ach', 'ACH')
        ],
        string="Payment Method",
        required=True,  # Campo obligatorio
        track_visibility='onchange'  # Habilita trazabilidad en cambios
    ) # Este parametro indica el sistema su comportamiento:
    # 1. Efectivo: Proceso de 2 Pasos
    #   a. Envio de Efectivo
    #   b. recibo de Efectivo
    # 2. Cheque: PRoceso de un solo paso; cuando la solicitud es aprobada, entonces:
    #   a. Se elabora el cheque
    #   b. Se entrega el ck para ser cambiarlo por efectivo en el banco    
    # 3. ACH: significa Automated Clearing House (Cámara de Compensación Automatizada).
    #    Es un sistema de pagos electrónicos que permite transferencias entre cuentas bancarias en los Estados Unidos.
    #    Es comúnmente utilizado para pagos como depósitos directos, transferencias de nómina, pagos de facturas,
    #    y otras transacciones electrónicas.

    expense_id = fields.Many2one('petty.cash.expense', string='Petty Cash Expense', tracking=1)
    # 2024-10-05: Nuevo campo para la razón de rechazo
    reject_reason = fields.Text('Reject Reason', tracking=True)
   
    def action_audit(self):
        """
        Método para marcar el documento de caja chica como 'auditado'.
        """
        for request in self:
            # Validar si la solicitud está en un estado que permite ser auditada
            if request.state not in ['approve']:
                raise ValidationError(_('Solo se pueden auditar las solicitudes aprobadas.'))

            # Cambiar el estado a 'audited'
            request.state = 'audited'
            # Aquí puedes agregar lógica adicional, como enviar notificaciones, etc.    
    
    def action_open_payment_form_opcion1(self):
        """Abrir el formulario de pagos con contexto personalizado"""
        self.ensure_one()

        # IDs de los diarios (ajusta estos valores según tu configuración)
        journal_payment_id = self.payment_journal_id.id  # Diario de pago (origen)
        petty_cash_journal_id = self.petty_journal_id.id  # Diario de caja chica (destino)
        amount = self.request_amount
        payment_type = 'outbound'
        # Preparar el contexto para pasar los diarios
        context = {
            'default_journal_id': journal_payment_id,  # Diario de pago (origen)
            'default_destination_journal_id': petty_cash_journal_id,  # Diario de caja chica (destino)
            'default_is_internal_transfer': True,  # Marcar como transferencia interna
            'default_amount': amount,
            'default_payment_type': payment_type
        }

        # Abrir el formulario account.payment.form con el contexto
        return {
            'name': 'Registrar Pago',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_form').id,
            'target': 'new',
            'context': context,
        }

    def action_state_petty_cash_payment(self):
        # Cambiar la cuenta contable de la segunda linea del asiento de diario
        # Cambiar el parametro: is_iinternal_tranfer a True; para que se pueda cambiar la cuenta contable de la segunda linea
        self.env['account.payment'].set_internal_transfer(self.payment_id.id)
        # Suponiendo que move_id y new_account_id son válidos
        move_id = self.payment_id.move_id.id  # ID del asiento de diario
        new_account_id = self.petty_journal_id.default_account_id.id  # ID de la nueva cuenta contable
        # Llamar al método para cambiar la cuenta de la segunda línea
        self.env['account.move'].change_second_line_account_sql(move_id, new_account_id)
        # Cambiar el estado de la Solicitud de Caja Chica - Pagado
        self.state = 'paid'
        #self.save()

    def action_open_payment_form(self):
        """Abrir el formulario de pagos con contexto personalizado y guardar el ID del pago"""
        self.ensure_one()

        # IDs de los diarios (ajusta estos valores según tu configuración)
        journal_payment_id = self.payment_journal_id.id  # Diario de pago (origen)
        petty_cash_journal_id = self.petty_journal_id.id  # Diario de caja chica (destino)
        amount = self.request_amount
        payment_type = 'outbound'
        if self.pay_method == 'cash':
            name_payment_method_id = 'manual'
        elif self.pay_method == 'cheque':
            name_payment_method_id = 'check_printing'
        elif self.pay_method == 'ach':
            name_payment_method_id = 'ach'
        else:
            name_payment_method_id = ''
            _message = "Método de Pago no definido en Caja Chica"
            raise UserError(_message)
        payment_method_id= self.env['account.payment.method'].search([('code','=',name_payment_method_id)],limit=1)
        payment_method_line_id = self.env['account.payment.method.line'].search([('journal_id','=',journal_payment_id),('payment_method_id','=',payment_method_id.id)],limit=1)
        # Crear el registro del Journal Primero
        # La tecnica de registrar el registro de diario primero NO FUNCIONA
        # Crear el pago y obtener su ID
        vals = {
            'journal_id': journal_payment_id,  # Diario de pago (origen)
            'destination_journal_id': petty_cash_journal_id,  # Diario de caja chica (destino)
            'is_internal_transfer': False,  # Marcar como transferencia interna
            'amount': amount,
            'payment_type': payment_type,
            'payment_method_id':payment_method_id and payment_method_id.id or False,
            'payment_method_line_id': payment_method_line_id and payment_method_line_id.id or False,
            'outstanding_account_id': self.payment_journal_id and self.payment_journal_id.default_account_id.id or False,
            'date':self.date,
            'payment_reference': self.note,
            'ref': self.note,
            #'name': self.name,
            'currency_id':self.currency_id and self.currency_id.id or False,
            'company_id':self.company_id and self.company_id.id or False,
            'partner_id':self.company_id.partner_id.id or False,
            'partner_type': 'supplier', #'customer'
        }
        payment = self.env['account.payment'].create(vals)

        # Guardar el ID del pago en el campo payment_id
        self.payment_id = payment.id
        # Postea la payment y genera contabilidad
        # self.payment_id.action_post()
        # Abrir el formulario account.payment.form con el contexto
        return {
            'name': 'Registrar Pago',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,  # Abrir el registro recién creado
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_form').id,
            'target': 'new',
            'context': dict(self.env.context, create=False),  # Evitar crear un nuevo pago
        }

    
    def action_register_payment(self):
        ''' Open the account.payment.register wizard to pay the selected journal entries.
        :return: An action opening the account.payment.register wizard.
        '''
        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.ids,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def action_register_payment_opcion2(self):
        """
        Set net to pay how default amount to pay
        """
        res = super().action_register_payment()
        amount_net_pay_residual = 0
        currency_id = self.currency_id
        if len(currency_id) > 1:
            raise UserError(_("Petty Cash Request must have the same currency"))
        for am in self:
            if am.request_amount:
                amount_net_pay_residual += am.request_amount
        if not currency_id.is_zero(amount_net_pay_residual):
            ctx = res.get("context", {})
            if ctx:
                ctx.update({"default_amount": amount_net_pay_residual})
            res.update({"context": ctx})
        return res

    @api.onchange('expense_id')
    def _onchange_expense_id(self):
        if self.expense_id:
            self.request_amount = self.expense_id.expense_amount
        else:
            self.request_amount = 0.0  # O cualquier valor por defecto que desees

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
            'account_id_cr': self.payment_journal_id and self.payment_journal_id.default_account_id.id or False,
            'payment_method_id':payment_method_id and payment_method_id.id or False,
            'destination_journal_id':self.petty_journal_id.id or False,
            'account_id_dr':self.petty_journal_id.default_account_id.id,
            'date':self.date,
            'description': self.note,
            'name': self.name,
            'transfer_account_id':self.payment_journal_id.company_id.transfer_account_id.id or False
        }
        return vals

        # Aquí podrías realizar acciones adicionales si es necesario, como confirmar el pago, etc.
        ##########################################################################################
        # payment_id = self.env['account.payment'].sudo().create(vals)
        # payment_id.action_post()
        # self.payment_id= payment_id and payment_id.id or False

        #######################################################################################
    def action_confirm_send(self):
        # CREACION DEL ENCABEZADO DEL REGISTRO DEL PAGO POR TRSANSGFERENCIA INTERNO
        # ASIENTO DEL DIARIO ORIGEN - PAYMENT
        #######################################################################################
        vals = self.create_payment()
        payment_cash_data = self.get_datos_factura(vals, 'payment_cash', 'origin')
        print(payment_cash_data)
        if payment_cash_data:
            # Transferencia de Efectivo o Liquidez
            # Asiento de Diario Origen de la Transferencia
            invoice_id = self.env['account.move'].create(payment_cash_data)
            invoice_id.action_post()
        else:
            raise UserError("Los datos del pago en efectivo están vacíos o no son válidos.")
        print(f"Transferencia Interna de Caja Chica creada con ID: {invoice_id}")
        self.account_move_ids_send = invoice_id
                            
    def action_confirm_receive(self):
        # REGISTRO EN MODELO: ACCOUNT.PAYMENT DE LA TRANSACCION
        # ASIENTO DEL DIARIO DESTINO - PETTY CASH (CAJA CHICA)
        vals = self.create_payment()        
        payment_cash_data = self.get_datos_factura(vals, 'payment_cash', 'destination')
        print(payment_cash_data)
        if payment_cash_data:
            # Transferencia de Efectivo o Liquidez
            # Asiento de Diario Destino de la Transferencia
            invoice_id = self.env['account.move'].create(payment_cash_data)
            invoice_id.action_post()
        else:
            raise UserError("Los datos del pago en efectivo están vacíos o no son válidos.")
        print(f"Transferencia Interna de Caja Chica creada con ID: {invoice_id}")
        self.account_move_ids_receive = invoice_id

    ##############################
    def get_datos_factura(self, vals, erp_origen=None, category=None):
        # Datos de la factura de partner (proveedor)
        if erp_origen =='payment_cash':
            if category == 'origin':
                invoice_data = self.get_datos_payment_cash_origin(vals)
            else:
                invoice_data = self.get_datos_payment_cash_destination(vals)
        else:
            invoice_data = None
        return invoice_data

    def get_datos_payment_cash_origin(self, vals):
        # ASIENTO DE DIARIO ORIGEN  DEBITO A LA CUENTA INTERNA DE TRANSFERENCIAS
        #                           CREDITO A LA CUENTA POR DEFAULT DEL DIARIO DE PAGO
        supplier_id = vals['partner_id']  # ID del proveedor
        # Datos del encabezado
        invoice_lines = [
            {
                'name': 'Crédito del Asiento de Solicitud de Caja Chica: ' + vals['name'],
                'quantity': 1,
                'price_unit': vals['amount'],
                'price_subtotal': vals['amount'],
                'price_total': vals['amount'],
                'account_id': vals['account_id_cr'],  # ID de la cuenta contable
                'debit':0.00,
                'credit':vals['amount'],
                'balance':-1*vals['amount'],
                'amount_currency': -1*vals['amount']
            },
            {
                'name': 'Débito del Asiento de Solicitud de Caja Chica: ' + vals['name'],
                'account_id': vals['transfer_account_id'],  # ID de la cuenta contable
                'debit': vals['amount'],
                'credit':0.00,
                'balance':vals['amount'],
                'amount_currency': vals['amount'],
                'amount_residual':vals['amount'],
                'amount_residual_currency':vals['amount'],
            }

        ]
        invoice_data = {
            'move_type': 'entry',
            'journal_id': vals['destination_journal_id'],
            'partner_id': supplier_id,
            'invoice_date': vals['date'],
            'date': vals['date'],
            'invoice_line_ids': [(0, 0, line) for line in invoice_lines],
            'currency_id': vals['currency_id'],  # ID de la moneda, normalmente 1 para EUR o USD
            'ref': vals['name'] + ' - ' + vals['description']
        }
        return invoice_data

    def get_datos_payment_cash_destination(self, vals):
        supplier_id = vals['partner_id']  # ID del proveedor
        # Datos del encabezado
        invoice_lines = [
            {
                #'product_id': None,  # ID del producto
                'name': 'Crédito del Asiento de Solicitud de Caja Chica:' + vals['name'],
                'quantity': 1,
                'price_unit': vals['amount'],
                'price_subtotal': vals['amount'],
                'price_total': vals['amount'],
                'account_id': vals['transfer_account_id'],  # ID de la cuenta contable
                'debit':0.00,
                'credit':vals['amount'],
                'balance':-1*vals['amount'],
                'amount_currency': -1*vals['amount']
            },
            {
                'name': 'Debito del Asiento de Solicitud Caja Chica:' + vals['name'],
                'account_id': vals['account_id_dr'],  # ID de la cuenta contable
                'debit': vals['amount'],
                'credit':0.00,
                'balance':vals['amount'],
                'amount_currency': vals['amount'],
                'amount_residual':vals['amount'],
                'amount_residual_currency':vals['amount'],
            }

        ]
        invoice_data = {
            'move_type': 'entry',
            'journal_id': vals['destination_journal_id'],
            'partner_id': supplier_id,
            'invoice_date': vals['date'],
            'date': vals['date'],
            'invoice_line_ids': [(0, 0, line) for line in invoice_lines],
            'currency_id': vals['currency_id'],  # ID de la moneda, normalmente 1 para EUR o USD
            'ref': vals['name'] + ' - ' + vals['description']
        }
        return invoice_data
    ##############################
    def action_request(self):
        if self.request_amount <= 0:
            raise ValidationError(_('Request Amount must be positive.'))
        self.state='request'
    
    def action_approve(self):
        if not self.note:
            raise ValidationError(_("You cannot approve a request without a description."))
        self.create_payment()
        self.state='approve'
    
    def action_cancel(self):
        self.state='cancel'
    
    def action_reject(self):
        """
        Método para rechazar la solicitud y especificar la razón del rechazo.
        """
        for request in self:
            # Verificar si hay una razón de rechazo proporcionada
            if not request.reject_reason:
                raise ValidationError(_('Debe proporcionar una razón para rechazar la solicitud.'))
            
            # Cambiar el estado a 'reject' y registrar la razón
            request.state = 'reject'    

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

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    petty_cash_request_id = fields.Many2one('petty.cash.request', string='Petty Cash Request', tracking=1)
    
    @api.constrains('petty_cash_request_id')
    def _check_unique_petty_cash_request(self):
        for record in self:
            if record.petty_cash_request_id:
                existing_payment = self.search([('petty_cash_request_id', '=', record.petty_cash_request_id.id), ('id', '!=', record.id)])
                if existing_payment:
                    raise ValidationError('La solicitud de caja chica ya tiene un pago asociado.')    
    
    @api.model
    def set_internal_transfer(self, payment_id):
        # Buscamos el registro del pago
        payment = self.browse(payment_id)
        
        # Validamos que exista el registro
        if not payment:
            return {'status': 'error', 'message': f'No se encontró el payment_id: {payment_id}'}
        
        # Actualizamos el campo is_internal_transfer
        payment.is_internal_transfer = True

        # Devolvemos una respuesta de éxito
        return {'status': 'success', 'message': f'Se actualizó el payment_id: {payment_id} a internal_transfer'}

class AccountMove(models.Model):
    _inherit = 'account.move'

    petty_cash_request_id_send = fields.Many2one(
        'petty.cash.request',
        string='Petty Cash Request (Send)',
        ondelete='cascade'
    )

    petty_cash_request_id_receive = fields.Many2one(
        'petty.cash.request',
        string='Petty Cash Request (Receive)',
        ondelete='cascade'
    )

    payment_priority = fields.Selection([
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low')
    ], string='Payment Priority', default='medium', help="Priority of payment for this invoice.")

    amount_tax_retention = fields.Float(string='Tax Retention Amount', help="Amount retained for tax purposes.")    

    def change_second_line_account(self, move_id, new_account_id):
        """
        Cambia la cuenta contable de la segunda línea de un asiento de diario dado.
        
        :param move_id: ID del asiento de diario (`account.move`) al que se le cambiará la cuenta.
        :param new_account_id: ID de la nueva cuenta contable (`account.account`) para la segunda línea.
        """
        # Buscar el asiento de diario con el ID proporcionado
        move = self.browse(move_id)

        # Verificar si el asiento tiene al menos dos líneas
        if len(move.line_ids) < 2:
            raise ValueError("El asiento de diario no tiene al menos dos líneas.")

        # Obtener la segunda línea y cambiar su cuenta
        second_line = move.line_ids[1]  # Las líneas son 0-indexadas, así que [1] es la segunda línea
        second_line.account_id = new_account_id

    @api.model
    def change_second_line_account_sql(self, move_id, new_account_id):
        """
        Cambia la cuenta contable de la segunda línea de un asiento de diario dado usando una consulta SQL.

        :param move_id: ID del asiento de diario (`account.move`) al que se le cambiará la cuenta.
        :param new_account_id: ID de la nueva cuenta contable (`account.account`) para la segunda línea.
        """
        # Obtener la segunda línea de 'account.move.line' usando SQL
        self.env.cr.execute("""
            SELECT id 
            FROM account_move_line 
            WHERE move_id = %s 
            ORDER BY id 
            LIMIT 1 OFFSET 1
        """, (move_id,))
        
        # Obtener el ID de la segunda línea
        result = self.env.cr.fetchone()
        
        if not result:
            raise ValueError("El asiento de diario no tiene al menos dos líneas.")
        
        second_line_id = result[0]

        # Actualizar la cuenta de la segunda línea
        self.env.cr.execute("""
            UPDATE account_move_line
            SET account_id = %s
            WHERE id = %s
        """, (new_account_id, second_line_id))

        # Forzar la invalidación de la caché para que otros métodos vean los cambios inmediatamente
        self.invalidate_cache()
