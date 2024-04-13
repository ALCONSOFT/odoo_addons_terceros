# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).
from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    knk_purchase_return_qty = fields.Float(string="Returned",
                                           compute="_return_qty_count")
    knk_purchase_balanced_qty = fields.Float(string="Balanced")

    def _return_qty_count(self):
        for rec in self:
            picks = rec.env['stock.picking'].search(
                [('id', 'in', rec.order_id.knk_picking_ids.ids),
                 ('state', '=', 'done')])
            qty = 0
            for pick in picks:
                lines = pick.move_ids_without_package
                for line in lines:
                    if line.purchase_line_id:
                        if line.purchase_line_id.id == rec.id:
                            qty += line.quantity_done
            rec.knk_purchase_return_qty = qty
            rec.knk_purchase_balanced_qty = (
                rec.qty_received - rec.knk_purchase_return_qty)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    out_picking_count = fields.Integer(string="outgoing shipments",
                                       compute="_compute_pick")
    picking_ids = fields.Many2many(
        'stock.picking', string='Receptions', copy=False, store=True)
    knk_purchase_return_show = fields.Boolean(compute="_get_is_shipped_value")
    knk_picking_ids = fields.Many2many(
        'stock.picking', 'return_picking_rel_purchase',
        string='Returns', copy=False, store=True)
    knk_return_ids = fields.One2many(
        'purchase.order.return', 'knk_purchase_order_id',
        string="Return Orders", readonly=True)

    @api.depends('picking_ids')
    def _get_is_shipped_value(self):
        for rec in self:
            rec.knk_purchase_return_show = False
            if rec.picking_ids and any(x.state in ['done', 'cancel'] for x in rec.picking_ids):
                rec.knk_purchase_return_show = True
            else:
                rec.knk_purchase_return_show = False

    @api.depends('knk_picking_ids')
    def _compute_pick(self):
        for rec in self:
            if rec.knk_picking_ids:
                rec.out_picking_count = len(rec.knk_picking_ids.ids)
            else:
                rec.out_picking_count = 0

    def action_view_out_picking(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all")
        pickings = self.mapped('knk_picking_ids')
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            form_view = [(self.env.ref('stock.view_picking_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [
                    (state, view) for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = pickings.id
        return action

    def purchase_return(self):
        ctxt = self.env.context.copy()
        ctxt.update({
            'default_knk_purchase_order_id': self.id,
        })
        return{
            'name': 'Returns',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.return',
            'view_mode': 'form',
            'target': 'new',
            'context': ctxt
        }





