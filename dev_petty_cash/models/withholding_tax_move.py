from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ExtendedWithholdingTaxMove(models.Model):
    _inherit = 'withholding.tax.move'

    def generate_account_move(self):
        """
        Creation of account moves to increase credit/debit vs tax authority.
        This method now supports creating multiple moves, one for each withholding tax.
        """
        for move in self:
            if move.wt_account_move_id:
                raise ValidationError(
                    _(f"Warning! Wt account move already exists: {move.wt_account_move_id.name}")
                )

            # Iterate over all withholding taxes for this move
            for withholding_tax in move.withholding_tax_id:
                move_vals = {
                    "ref": _(
                        "Imp.Ret. %(code)s - %(move)s",
                        code=withholding_tax.code,
                        move=move.credit_debit_line_id.move_id.name,
                    ),
                    "journal_id": withholding_tax.journal_id.id,
                    "date": move.payment_line_id.move_id.date,
                }
                move_lines = self._prepare_move_lines(withholding_tax, move)
                move_vals["line_ids"] = move_lines

                # Create the move for each withholding tax
                move_entry = (
                    self.env["account.move"]
                    .with_context(default_move_type="entry")
                    .create(move_vals)
                )
                move_entry.action_post()

                # Link the move to the withholding tax move
                move.wt_account_move_id = move_entry.id

                # Reconcile if applicable
                self._reconcile_move_lines(move, move_entry)

    def _prepare_move_lines(self, withholding_tax, move):
        """
        Prepare move lines for the given withholding tax and the related move.
        """
        move_lines = []
        for _type in ("partner", "tax"):
            ml_vals = {
                "ref": _(
                    "WT %(code)s - %(partner)s - %(move)s",
                    code=withholding_tax.code,
                    partner=move.partner_id.name,
                    move=move.credit_debit_line_id.move_id.name,
                ),
                "name": "%s" % (move.credit_debit_line_id.move_id.name),
                "date": move.payment_line_id.move_id.date,
            }

            # Logic for partner or tax line
            if _type == "partner":
                ml_vals.update({
                    "partner_id": move.payment_line_id.partner_id.id,
                    "account_id": move.credit_debit_line_id.account_id.id,
                })
                if move.payment_line_id.credit:
                    ml_vals["credit"] = abs(move.amount)
                else:
                    ml_vals["debit"] = abs(move.amount)
            elif _type == "tax":
                ml_vals["name"] = "{} - {}".format(
                    withholding_tax.code, move.credit_debit_line_id.move_id.name
                )
                if move.payment_line_id.credit:
                    ml_vals["debit"] = abs(move.amount)
                    if move.credit_debit_line_id.move_id.move_type in [
                        "in_refund", "out_refund"
                    ]:
                        ml_vals["account_id"] = withholding_tax.account_payable_id.id
                    else:
                        ml_vals["account_id"] = withholding_tax.account_receivable_id.id
                else:
                    ml_vals["credit"] = abs(move.amount)
                    if move.credit_debit_line_id.move_id.move_type in [
                        "in_refund", "out_refund"
                    ]:
                        ml_vals["account_id"] = withholding_tax.account_receivable_id.id
                    else:
                        ml_vals["account_id"] = withholding_tax.account_payable_id.id

            move_lines.append((0, 0, ml_vals))

        return move_lines

    def _reconcile_move_lines(self, move, move_entry):
        """
        Reconcile the move lines created for the withholding tax.
        """
        line_to_reconcile = False
        for line in move_entry.line_ids:
            if (
                line.account_id.account_type in ["liability_payable", "asset_receivable"]
                and line.partner_id
            ):
                line_to_reconcile = line
                break
        if line_to_reconcile:
            if move.credit_debit_line_id.move_id.move_type in [
                "in_refund", "out_invoice"
            ]:
                debit_move_id = move.credit_debit_line_id.id
                credit_move_id = line_to_reconcile.id
            else:
                debit_move_id = line_to_reconcile.id
                credit_move_id = move.credit_debit_line_id.id

            self.env["account.partial.reconcile"].with_context(
                no_generate_wt_move=True
            ).create(
                {
                    "debit_move_id": debit_move_id,
                    "credit_move_id": credit_move_id,
                    "amount": abs(move.amount),
                    "credit_amount_currency": abs(move.amount),
                    "debit_amount_currency": abs(move.amount),
                }
            )
