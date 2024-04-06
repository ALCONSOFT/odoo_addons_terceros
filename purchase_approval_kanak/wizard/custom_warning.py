# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

from odoo import models, _


class CustomWarning(models.TransientModel):
    _name = 'custom.warning'
    _description = 'Custom Warning'

    def action_continue(self):
        active_id = self.env.context.get('active_id')
        if active_id and self.env.context.get('purchase_order'):
            purchase_order = self.env['purchase.order'].browse(active_id)
            if purchase_order.purchase_order_approval_rule_ids:
                purchase_order.message_subscribe(
                    partner_ids=purchase_order.purchase_order_approval_rule_ids.mapped(
                        'users.partner_id.id'))
                msg = _("RFQ is waiting for approval.")
                purchase_order.message_post(body=msg, subtype='mail.mt_comment')
            purchase_order.write({'send_for_approval': True})
        return True
