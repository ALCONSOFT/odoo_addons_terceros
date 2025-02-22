# Copyright (C) 2021, Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
import math
from odoo.tools import (
    date_utils,
    email_re,
    email_split,
    float_compare,
    float_is_zero,
    float_repr,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    groupby,
    is_html_empty,
    sql
)

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
from odoo.tools.float_utils import float_compare

try:
    from num2words import num2words
except ImportError:
    logging.getLogger(__name__).warning(
        "The num2words python library is not installed."
    )
    num2words = None


MAP_INVOICE_TYPE_PARTNER_TYPE = {
    "out_invoice": "customer",
    "out_refund": "customer",
    "in_invoice": "supplier",
    "in_refund": "supplier",
}

# Since invoice amounts are unsigned,
# this is how we know if money comes in or goes out
MAP_INVOICE_TYPE_PAYMENT_SIGN = {
    "out_invoice": 1,
    "in_refund": 1,
    "in_invoice": -1,
    "out_refund": -1,
}


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends("invoice_payments.amount")
    def _compute_total(self):
        self.total_amount = sum(line.amount for line in self.invoice_payments)

    @api.depends("invoice_payments.balance")
    def _compute_cheque_amount(self):
        # self.cheque_amount = sum(line.balance for line in self.invoice_payments)
        sumw = 0
        for line in self.invoice_payments:
            if line.invoice_id.withholding_tax:
                sumw = sumw + line.amount
            else:
                sumw = sumw + 0
        self.cheque_amount = sumw

    is_auto_fill = fields.Char(string="Auto-Fill Pay Amount")
    invoice_payments = fields.One2many(
        "invoice.payment.line", "wizard_id", string="Payments"
    )
    is_customer = fields.Boolean(string="Is Customer?")
    cheque_amount = fields.Float(
        "Batch Payment Total",
        required=True,
        compute="_compute_cheque_amount",
        store=True,
        readonly=False,
    )
    total_amount = fields.Float("Total Invoices:", compute="_compute_total")

    def get_invoice_payment_line(self, invoice):
        if invoice.withholding_tax:
            return (
                0,
                0,
                {
                    "partner_id": invoice.partner_id.id,
                    "invoice_id": invoice.id,
                    "balance": invoice.amount_residual or 0.0,
                    "amount": invoice.amount_net_pay_residual or 0.0,
                    "payment_difference": invoice.withholding_tax_amount or 0.0,
                    "payment_difference_handling": "open",
                    "note": "Keep Open %s" % invoice.name,
                },
            )
        else:
            return (
                0,
                0,
                {
                    "partner_id": invoice.partner_id.id,
                    "invoice_id": invoice.id,
                    "balance": invoice.amount_residual or 0.0,
                    "amount": invoice.amount_residual or 0.0,
                    "payment_difference": 0.0,
                    "payment_difference_handling": "reconcile",
                    "note": "Payment of invoice %s" % invoice.name,
                },
            )

    def get_invoice_payments(self, invoices):
        res = []
        for invoice in invoices:
            res.append(self.get_invoice_payment_line(invoice))
        return res

    @api.model
    def default_get(self, fields_list):
        if self.env.context and not self.env.context.get("batch", False):
            return super().default_get(fields_list)
        res = super().default_get(fields_list)
        context = dict(self._context or {})
        active_model = context.get("active_model")
        active_ids = context.get("active_ids")
        # Checks on context parameters
        if not active_model or not active_ids:
            raise UserError(
                _(
                    "The wizard is executed without active_model or active_ids in the context."
                )
            )
        if active_model != "account.move":
            raise UserError(
                _("The expected model for this action is 'account.move', not '%s'.")
                % active_model
            )
        # Checks on received invoice records
        invoices = self.env[active_model].browse(active_ids)
        if any(
            invoice.state != "posted"
            or invoice.payment_state not in ["not_paid", "partial"]
            for invoice in invoices
        ):
            raise UserError(_("You can only register payments for open invoices."))

        if any(inv.payment_mode_id != invoices[0].payment_mode_id for inv in invoices):
            raise UserError(
                _(
                    "You can only register a batch payment for"
                    " invoices with the same payment mode."
                )
            )
        if any(
            MAP_INVOICE_TYPE_PARTNER_TYPE[inv.move_type]
            != MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type]
            for inv in invoices
        ):
            raise UserError(
                _(
                    "You cannot mix customer invoices and vendor bills in a single payment."
                )
            )
        if any(inv.currency_id != invoices[0].currency_id for inv in invoices):
            raise UserError(
                _(
                    "In order to pay multiple bills at once, they must use the same currency."
                )
            )

        if "batch" in context and context.get("batch"):
            is_customer = (
                MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type] == "customer"
            )
            payment_lines = self.get_invoice_payments(invoices)
            res.update({"invoice_payments": payment_lines, "is_customer": is_customer})
        else:
            # Checks on received invoice records
            if any(
                MAP_INVOICE_TYPE_PARTNER_TYPE[inv.move_type]
                != MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type]
                for inv in invoices
            ):
                raise UserError(
                    _(
                        "You cannot mix customer invoices and vendor bills in a single payment."
                    )
                )

        total_amount = sum(
            inv.amount_residual * MAP_INVOICE_TYPE_PAYMENT_SIGN[inv.move_type]
            for inv in invoices
        )
        date_format = self.env["res.lang"]._lang_get(self.env.user.lang).date_format
        communication = "Batch payment of %s" % fields.Date.today().strftime(
            date_format
        )
        res.update(
            {
                "amount": abs(total_amount),
                "currency_id": invoices[0].currency_id.id,
                "payment_type": is_customer and "outbound" or "inbound",
                "partner_id": invoices[0].commercial_partner_id.id,
                "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type],
                "company_id": self.env.user.company_id.id,
                "communication": communication,
            }
        )
        return res

    def get_payment_values(self, group_data=None):
        if not group_data:
            return {}
        res = {
            "journal_id": self.journal_id.id,
            "payment_method_line_id": "payment_method_line_id" in group_data
            and group_data["payment_method_line_id"]
            or self.payment_method_line_id.id,
            "date": self.payment_date,
            "ref": group_data["memo"],
            "payment_type": self.payment_type,
            "amount": group_data["total"],
            "currency_id": self.currency_id.id,
            "partner_bank_id": self.partner_bank_id.id,
            "partner_id": int(group_data["partner_id"]),
            "partner_type": group_data["partner_type"],
            "check_amount_in_words": group_data["check_amount_in_words"],
            "write_off_line_vals": [],
        }
        conversion_rate = self.env["res.currency"]._get_conversion_rate(
            self.currency_id,
            self.company_id.currency_id,
            self.company_id,
            self.payment_date,
        )
        for invoice_id in list(group_data["inv_val"]):
            values = group_data["inv_val"][invoice_id]
            if (
                self.currency_id
                and not self.currency_id.is_zero(values["payment_difference"])
                and values["payment_difference_handling"] == "reconcile"
            ):
                writeoff_name = values.get("line_name", False)
                writeoff_account_id = values.get("writeoff_account_id", False)
                if self.payment_type == "inbound":
                    write_off_amount_currency = values["payment_difference"]
                else:
                    write_off_amount_currency = -values["payment_difference"]
                write_off_balance = self.company_id.currency_id.round(
                    write_off_amount_currency * conversion_rate
                )
                res["write_off_line_vals"].append(
                    {
                        "name": writeoff_name,
                        "account_id": writeoff_account_id,
                        "partner_id": self.partner_id.id,
                        "currency_id": self.currency_id.id,
                        "amount_currency": write_off_amount_currency,
                        "balance": write_off_balance,
                    }
                )
        return res

    def _check_amounts(self):
        if float_compare(self.total_amount, self.cheque_amount, 2) != 0:
            raise ValidationError(
                _(
                    "The pay amount of the invoices and the batch payment total do not match."
                )
            )

    def get_memo(self, memo, group_data, partner_id, data_get):
        if memo:
            memo = (
                group_data[partner_id]["memo"]
                + " : "
                + memo
                + "-"
                + str(data_get.invoice_id.name)
            )
        else:
            memo = (
                group_data[partner_id]["memo"] + " : " + str(data_get.invoice_id.name)
            )
        return memo

    def total_amount_in_words(self, data_get, old_total=0):
        check_amount_in_words = num2words(
            math.floor(old_total + data_get.amount)
        ).title()
        decimals = (old_total + data_get.amount) % 1
        if decimals >= 10**-2:
            check_amount_in_words += _(" and %s/100") % str(
                int(round(float_round(decimals * 100, precision_rounding=1)))
            )
        return check_amount_in_words

    def get_payment_invoice_value(self, name, data_get):
        return {
            "line_name": name,
            "amount": data_get.amount,
            "payment_difference_handling": data_get.payment_difference_handling,
            "payment_difference": data_get.payment_difference,
            "writeoff_account_id": data_get.writeoff_account_id
            and data_get.writeoff_account_id.id
            or False,
        }

    def update_group_pay_data(
        self, partner_id, group_data, data_get, check_amount_in_words
    ):
        # build memo value
        if self.communication:
            memo = self.communication + "-" + str(data_get.invoice_id.name)
        else:
            memo = str(data_get.invoice_id.name)
        name = ""
        if data_get.reason_code:
            name = str(data_get.reason_code.code)
        if data_get.note:
            name = name + ": " + str(data_get.note)
        if not name:
            name = "Counterpart"
        inv_val = {
            "line_name": name,
            "amount": data_get.amount,
            "payment_difference_handling": data_get.payment_difference_handling,
            "payment_difference": data_get.payment_difference,
            "writeoff_account_id": data_get.writeoff_account_id
            and data_get.writeoff_account_id.id
            or False,
        }
        group_data.update(
            {
                partner_id: {
                    "partner_id": partner_id,
                    "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[
                        data_get.invoice_id.move_type
                    ],
                    "total": data_get.amount,
                    "check_amount_in_words": check_amount_in_words,
                    "memo": memo,
                    "temp_invoice": data_get.invoice_id.id,
                    "inv_val": {data_get.invoice_id.id: inv_val},
                }
            }
        )

    def get_amount(self, memo, group_data, line):
        line.payment_difference = line.balance - line.amount
        partner_id = line.invoice_id.partner_id.id
        if partner_id in group_data:
            old_total = group_data[partner_id]["total"]
            # build memo value
            if self.communication:
                memo = (
                    group_data[partner_id]["memo"]
                    + " : "
                    + self.communication
                    + "-"
                    + str(line.invoice_id.name)
                )
            else:
                memo = (
                    group_data[partner_id]["memo"] + " : " + str(line.invoice_id.name)
                )
            # Calculate amount in words
            check_amount_in_words = self.total_amount_in_words(line, old_total)
            group_data[partner_id].update(
                {
                    "partner_id": partner_id,
                    "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[
                        line.invoice_id.move_type
                    ],
                    "total": old_total + line.amount,
                    "memo": memo,
                    "temp_invoice": line.invoice_id.id,
                    "check_amount_in_words": check_amount_in_words,
                }
            )
            # prepare name
            name = ""
            if line.reason_code:
                name = str(line.reason_code.code)
            if line.note:
                name = name + ": " + str(line.note)
            if not name:
                name = "Counterpart"
            # Update with payment diff data
            inv_val = self.get_payment_invoice_value(name, line)
            group_data[partner_id]["inv_val"].update({line.invoice_id.id: inv_val})
        else:
            # calculate amount in words
            check_amount_in_words = self.total_amount_in_words(line, 0)
            # prepare name
            self.update_group_pay_data(
                partner_id, group_data, line, check_amount_in_words
            )

    def _reconcile_open_invoices(
        self,
        line,
        inv,
        amount_residual,
        amount_residual_currency,
        reconciled,
        amount,
        debit_amount_currency,
        credit_amount_currency,
    ):
        acc_part_recnc_obj = self.env["account.partial.reconcile"]
        line.update(
            {
                "amount_residual": amount_residual,
                "amount_residual_currency": amount_residual_currency,
                "reconciled": reconciled,
            }
        )
        if inv.move_type == "out_invoice":
            part_rec_domain = [("debit_move_id", "=", line.id)]
        elif inv.move_type == "in_invoice":
            part_rec_domain = [("credit_move_id", "=", line.id)]
        partial = acc_part_recnc_obj.search(part_rec_domain, limit=1)
        if partial:
            partial.update(
                {
                    "amount": amount,
                    "debit_amount_currency": debit_amount_currency,
                    "credit_amount_currency": credit_amount_currency,
                }
            )

    def make_payments(self):
        # Make group data either for Customers or Vendors
        context = dict(self._context or {})
        group_data = {}
        memo = self.communication or " "
        context.update({"is_customer": self.is_customer})
        self._check_amounts()
        for invoice_payment_line in self.invoice_payments:
            if invoice_payment_line.amount > 0:
                self.get_amount(memo, group_data, invoice_payment_line)
        # update context
        context.update({"group_data": group_data})
        # making partner wise payment
        payment_ids = []
        for partner in list(group_data):
            # update active_ids with active invoice ids
            if context.get("active_ids", False) and group_data[partner].get(
                "inv_val", False
            ):
                context.update({"active_ids": list(group_data[partner]["inv_val"])})
            payment = (
                self.env["account.payment"]  # pylint: disable=context-overridden
                .with_context(context)
                .create(self.get_payment_values(group_data=group_data[partner]))
            )
            payment_ids.append(payment.id)
            payment.action_post()

            # Reconciliation
            def _get_line_filter(line):
                line_filter = (
                    line.account_id
                    and line.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                    and not line.reconciled
                )
                return line_filter

            payment_lines = payment.line_ids.filtered(_get_line_filter)
            invoices = self.env["account.move"].browse(context.get("active_ids"))
            lines = invoices.line_ids.filtered(_get_line_filter)
            for account in payment_lines.account_id:
                (payment_lines + lines).filtered_domain(
                    [("account_id", "=", account.id), ("reconciled", "=", False)]
                ).reconcile()
            if any(
                group_data[partner]["inv_val"][inv.id]["payment_difference_handling"]
                == "open"
                for inv in invoices
            ):
                for inv in invoices:
                    if (
                        group_data[partner]["inv_val"][inv.id][
                            "payment_difference_handling"
                        ]
                        == "open"
                    ):
                        payment_state = "partial"
                    else:
                        payment_state = "paid"
                    for line in inv.line_ids:
                        if line.amount_residual > 0 and payment_state == "paid":
                            line_amount = 0.0
                            partial_amount = group_data[partner]["inv_val"][inv.id][
                                "amount"
                            ]
                            self._reconcile_open_invoices(
                                line,
                                inv,
                                line_amount,
                                line_amount,
                                True,
                                partial_amount,
                                partial_amount,
                                partial_amount,
                            )
                            continue
                        if line.reconciled and payment_state == "partial":
                            line_amount = group_data[partner]["inv_val"][inv.id][
                                "payment_difference"
                            ]
                            partial_amount = group_data[partner]["inv_val"][inv.id][
                                "amount"
                            ]
                            self._reconcile_open_invoices(
                                line,
                                inv,
                                line_amount,
                                line_amount,
                                False,
                                partial_amount,
                                partial_amount,
                                partial_amount,
                            )
                            continue
                    inv.update(
                        {
                            "payment_state": payment_state,
                            "amount_residual": group_data[partner]["inv_val"][inv.id][
                                "payment_difference"
                            ],
                            "amount_residual_signed": group_data[partner]["inv_val"][
                                inv.id
                            ]["payment_difference"],
                        }
                    )
                    inv._compute_payments_widget_reconciled_info()
        view_id = self.env.ref(
            "account_payment_batch_process.view_account_payment_tree_nocreate"
        ).id
        return {
            "name": _("Payments"),
            "view_type": "form",
            "view_mode": "tree",
            "res_model": "account.payment",
            "view_id": view_id,
            "type": "ir.actions.act_window",
            "target": "new",
            "domain": "[('id','in',%s)]" % (payment_ids),
            "context": {"group_by": "partner_id"},
        }
    
    def corregir_amount_residual(self):
        # Obtener los IDs de las facturas relacionadas
        invoice_ids = self.line_ids.mapped('move_id.id')

        if invoice_ids:
            # Crear la sentencia SQL para actualizar el campo amount_residual a 0.0
            query = """
                UPDATE account_move
                SET amount_residual = 0.0
                WHERE id IN %s
            """

            # Ejecutar la consulta SQL
            self.env.cr.execute(query, (tuple(invoice_ids),))

        pass

    def corregir_amount_net_to_pay_residual(self):
        pass

    def get_batch_payment_amount(self, invoice=None, payment_date=None):
        return {
            "amount": False,
            "payment_difference": False,
            "payment_difference_handling": False,
            "writeoff_account_id": False,
        }

    def get_invoice_payments_remaining_amount(self, remaining_amount, count):
        total = 0.0
        for payline in self.invoice_payments:
            vals = self.get_batch_payment_amount(payline.invoice_id, self.payment_date)
            if remaining_amount < 0.0:
                break
            amount = vals.get("amt", False) or payline.balance
            total += amount
            payline.write(
                {
                    "amount": vals.get("amount", False) or payline.balance,
                    "payment_difference": vals.get("payment_difference", False) or 0.0,
                    "writeoff_account_id": vals.get("writeoff_account_id", False),
                    "payment_difference_handling": vals.get(
                        "payment_difference_handling", False
                    )
                    or "open",
                    "note": vals.get("note", False),
                }
            )
        self.cheque_amount = total

    def auto_fill_payments(self):
        ctx = self._context.copy()
        batch_payment = self.cheque_amount
        remaining_amt = batch_payment
        count = 0
        for wizard in self:
            if wizard.invoice_payments:
                wizard.get_invoice_payments_remaining_amount(remaining_amt, count)
            ctx.update(
                {
                    "reference": wizard.communication or "",
                    "journal_id": wizard.journal_id.id,
                }
            )
        return {
            "name": _("Batch Payments"),
            "view_mode": "form",
            "view_id": False,
            "view_type": "form",
            "res_id": self.id,
            "res_model": "account.payment.register",
            "type": "ir.actions.act_window",
            "nodestroy": True,
            "target": "new",
            "context": ctx,
        }

class AccountMove(models.Model):
    _inherit = 'account.move'

    amount_residual = fields.Monetary(
        string='Amount Due',
        compute='_compute_amount',  # default=lambda self: self._compute_amount(),
        store=True,
    )

    def _compute_amount(self):
        for move in self:
            total_untaxed, total_untaxed_currency = 0.0, 0.0
            total_tax, total_tax_currency = 0.0, 0.0
            total_residual, total_residual_currency = 0.0, 0.0
            total, total_currency = 0.0, 0.0

            for line in move.line_ids:
                if move.is_invoice(True):
                    # === Invoices ===
                    if line.display_type == 'tax' or (line.display_type == 'rounding' and line.tax_repartition_line_id):
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type in ('product', 'rounding'):
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type == 'payment_term':
                        # Residual amount.
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            sign = move.direction_sign
            move.amount_untaxed = sign * total_untaxed_currency
            move.amount_tax = sign * total_tax_currency
            move.amount_total = sign * total_currency
            if move.withholding_tax and move.move_type == 'in_invoice':
                # Buscar la factura
                ll_pagos, pagos_a_factura_widget = self.obtener_pagos_a_factura(move.invoice_payments_widget)
                # if move.amount_net_pay < pagos_a_factura_widget:
                #     pagos_a_factura = move.amount_net_pay
                # else:
                #     pagos_a_factura = pagos_a_factura_widget
                if move.amount_total <= pagos_a_factura_widget:    # + move.withholding_tax_amount:
                    # move.amount_residual = -sign * total_residual_currency
                    move.amount_residual = 0.0
                    move.amount_net_pay_residual = -sign * move.withholding_tax_amount
                else:
                    move.amount_residual = -sign * total_residual_currency
            else:
                move.amount_residual = -sign * total_residual_currency
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
            move.amount_residual_signed = total_residual
            move.amount_total_in_currency_signed = abs(move.amount_total) if move.move_type == 'entry' else -(sign * move.amount_total)

    def obtener_pagos_a_factura(self, payments_widget):
        # Verificar si payments_widget no es None o False y tiene el formato esperado
        if payments_widget and isinstance(payments_widget, dict) and 'content' in payments_widget:
            # Inicializar una lista para almacenar los montos de cada pago
            amounts = []
            total_amount = 0.0
            # Iterar sobre los elementos dentro de 'content'
            for payment in payments_widget['content']:
                # Verificar si 'amount' está presente en el diccionario actual
                if 'amount' in payment:
                    # Agregar el valor del monto a la lista
                    amounts.append(payment['amount'])
                    total_amount += payment['amount']
            # Mostrar los valores obtenidos y el total de los montos
            print("Montos de pagos:", amounts)
            print(f"Total de montos: {total_amount}")
            return amounts, total_amount
        # Si payments_widget no tiene el formato esperado, retorna valores por defecto
        return [], 0.0

    @api.depends('move_type', 'line_ids.amount_residual')
    def _compute_payments_widget_reconciled_info(self):
        for move in self:
            payments_widget_vals = {'title': _('Less Payment'), 'outstanding': False, 'content': []}

            if move.state == 'posted' and move.is_invoice(include_receipts=True):
                reconciled_vals = []
                reconciled_partials = move._get_all_reconciled_invoice_partials()
                for reconciled_partial in reconciled_partials:
                    counterpart_line = reconciled_partial['aml']
                    if counterpart_line.move_id.ref:
                        reconciliation_ref = '%s (%s)' % (counterpart_line.move_id.name, counterpart_line.move_id.ref)
                    else:
                        reconciliation_ref = counterpart_line.move_id.name
                    if counterpart_line.amount_currency and counterpart_line.currency_id != counterpart_line.company_id.currency_id:
                        foreign_currency = counterpart_line.currency_id
                    else:
                        foreign_currency = False

                    reconciled_vals.append({
                        'name': counterpart_line.name,
                        'journal_name': counterpart_line.journal_id.name,
                        'amount': reconciled_partial['amount_total'] if reconciled_partial['amount_total'] <= reconciled_partial['amount'] else reconciled_partial['amount'],
                        'currency_id': move.company_id.currency_id.id if reconciled_partial['is_exchange'] else reconciled_partial['currency'].id,
                        'date': counterpart_line.date,
                        'partial_id': reconciled_partial['partial_id'],
                        'account_payment_id': counterpart_line.payment_id.id,
                        'payment_method_name': counterpart_line.payment_id.payment_method_line_id.name,
                        'move_id': counterpart_line.move_id.id,
                        'ref': reconciliation_ref,
                        # these are necessary for the views to change depending on the values
                        'is_exchange': reconciled_partial['is_exchange'],
                        'amount_company_currency': formatLang(self.env, abs(counterpart_line.balance), currency_obj=counterpart_line.company_id.currency_id),
                        'amount_foreign_currency': foreign_currency and formatLang(self.env, abs(counterpart_line.amount_currency), currency_obj=foreign_currency)
                    })
                payments_widget_vals['content'] = reconciled_vals

            if payments_widget_vals['content']:
                move.invoice_payments_widget = payments_widget_vals
            else:
                move.invoice_payments_widget = False

    def _get_all_reconciled_invoice_partials(self):
        self.ensure_one()
        reconciled_lines = self.line_ids.filtered(lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable'))
        if not reconciled_lines:
            return {}

        self.env['account.partial.reconcile'].flush_model([
            'credit_amount_currency', 'credit_move_id', 'debit_amount_currency',
            'debit_move_id', 'exchange_move_id',
        ])
        query = '''
            SELECT
                part.id,
                part.exchange_move_id,
                part.debit_amount_currency AS amount,
                part.credit_move_id AS counterpart_line_id,
                part.amount AS amount_total
            FROM account_partial_reconcile part
            WHERE part.debit_move_id IN %s

            UNION ALL

            SELECT
                part.id,
                part.exchange_move_id,
                part.credit_amount_currency AS amount,
                part.debit_move_id AS counterpart_line_id,
                part.amount AS amount_total
            FROM account_partial_reconcile part
            WHERE part.credit_move_id IN %s
        '''
        self._cr.execute(query, [tuple(reconciled_lines.ids)] * 2)

        partial_values_list = []
        counterpart_line_ids = set()
        exchange_move_ids = set()
        for values in self._cr.dictfetchall():
            partial_values_list.append({
                'aml_id': values['counterpart_line_id'],
                'partial_id': values['id'],
                'amount': values['amount'],
                'currency': self.currency_id,
                'amount_total':values['amount_total']
            })
            counterpart_line_ids.add(values['counterpart_line_id'])
            if values['exchange_move_id']:
                exchange_move_ids.add(values['exchange_move_id'])

        if exchange_move_ids:
            self.env['account.move.line'].flush_model(['move_id'])
            query = '''
                SELECT
                    part.id,
                    part.credit_move_id AS counterpart_line_id
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                WHERE credit_line.move_id IN %s AND part.debit_move_id IN %s

                UNION ALL

                SELECT
                    part.id,
                    part.debit_move_id AS counterpart_line_id
                FROM account_partial_reconcile part
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
                WHERE debit_line.move_id IN %s AND part.credit_move_id IN %s
            '''
            self._cr.execute(query, [tuple(exchange_move_ids), tuple(counterpart_line_ids)] * 2)

            for values in self._cr.dictfetchall():
                counterpart_line_ids.add(values['counterpart_line_id'])
                partial_values_list.append({
                    'aml_id': values['counterpart_line_id'],
                    'partial_id': values['id'],
                    'currency': self.company_id.currency_id,
                })

        counterpart_lines = {x.id: x for x in self.env['account.move.line'].browse(counterpart_line_ids)}
        for partial_values in partial_values_list:
            partial_values['aml'] = counterpart_lines[partial_values['aml_id']]
            partial_values['is_exchange'] = partial_values['aml'].move_id.id in exchange_move_ids
            if partial_values['is_exchange']:
                partial_values['amount'] = abs(partial_values['aml'].balance)

        return partial_values_list
