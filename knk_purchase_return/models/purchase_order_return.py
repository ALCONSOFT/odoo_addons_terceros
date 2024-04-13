# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrderReturn(models.Model):
    _name = 'purchase.order.return'
    _description = "Returns for purchase order"
    _inherit = ['portal.mixin', 'mail.thread',
                'mail.activity.mixin', 'utm.mixin']

    @api.model
    def _get_default_team(self):
        return self.env['crm.team']._get_default_team_id()

    name = fields.Char(string='Return Order',
                       required=True,
                       copy=False,
                       readonly=True,
                       default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string="Customer")
    date_of_return = fields.Datetime(
        string="Return Date", default=datetime.today())
    knk_purchase_order_id = fields.Many2one(
        'purchase.order', domain="[('partner_id', '=', partner_id)]", string="Return of")
    knk_purchase_order_return_line_ids = fields.One2many(
        'purchase.order.return.line', 'knk_purchase_return_id')
    product_ids = fields.Many2many('product.product', string="Products")
    note = fields.Text()
    user_id = fields.Many2one(
        'res.users', string='Purchase Representative',
        default=lambda self: self.env.user,)
    company_id = fields.Many2one(
        'res.company', 'Company',
        required=True, index=True, default=lambda self: self.env.company)
    state = fields.Selection([('draft', 'Draft'),
                              ('confirm', 'Return Order')], default='draft',
                             tracking=True)
    knk_picking_ids = fields.Many2many('stock.picking', 'return_purchase_order_picking_rel',
                                       'return_id', 'stock_pick_id',
                                       string='Returns',
                                       copy=False, store=True)
    outgoing_count = fields.Integer(string="Outgoing shipments",
                                    compute="_compute_picks")

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            if val.get('name', _('New')) == _('New'):
                val['name'] = self.env['ir.sequence'].\
                    next_by_code('purchase.order.return')
        return super().create(vals)

    @api.depends('knk_picking_ids')
    def _compute_picks(self):
        for rec in self:
            if rec.knk_picking_ids:
                rec.outgoing_count = len(rec.knk_picking_ids.ids)
            else:
                rec.outgoing_count = 0

    @api.onchange('partner_id')
    def _reset_purchase_details(self):
        self.write({
            'user_id': False,
            'company_id': False,
            'knk_purchase_order_id': False,
            'knk_purchase_order_return_line_ids': False,
        })

    @api.onchange('knk_purchase_order_id')
    def _get_purchase_details(self):
        values_list = []
        for lines in self.knk_purchase_order_id.order_line:
            values_list.append([0, 0, {
                'knk_product_id': lines.product_id.id,
                'knk_product_qty': 0
            }])
        self.write({"knk_purchase_order_return_line_ids": False})
        self.write({"knk_purchase_order_return_line_ids": values_list})

        if self.knk_purchase_order_id:
            self.user_id = self.knk_purchase_order_id.user_id
            self.company_id = self.knk_purchase_order_id.company_id

    def button_confirm(self):
        for line in range(len(self.knk_purchase_order_return_line_ids)):
            if (
                self.knk_purchase_order_return_line_ids[line].
                knk_product_qty > self.knk_purchase_order_id.order_line[line]
                .knk_purchase_balanced_qty or
                self.knk_purchase_order_return_line_ids[line]
                .knk_product_qty > self.knk_purchase_order_id.order_line[line].qty_received
            ):
                raise UserError(
                    "Return quantity cannot be more than Delivered Quantity"
                )

        picking_type_id = self.env['stock.picking.type'].search(
            [('code', '=', 'outgoing'),
             ('company_id', '=', self.company_id.id)], limit=1)
        if picking_type_id:
            res = self._prepare_picking(self, picking_type_id)
            new_picking_id = self.env['stock.picking'].create(res)
            self.knk_purchase_order_id.knk_picking_ids = [
                (4, new_picking_id.id, 0)]
            self.knk_picking_ids = [(4, new_picking_id.id, 0)]
            lines = self.knk_purchase_order_return_line_ids
            for line in range(len(lines)):
                purchase_val_id = lines[line].knk_purchase_return_id.\
                    knk_purchase_order_id.order_line[line].id
                move_vals = self._prepare_stock_moves(
                    self, lines[line], picking_type_id, new_picking_id, purchase_val_id)
                for move_val in move_vals:
                    self.env['stock.move'].create(
                        move_val)._action_confirm()._action_assign()
                self.env.cr.commit()
            self.process(new_picking_id)
            self.state = 'confirm'
            try:
                res = new_picking_id.button_validate()
                if res:
                    if res.get('res_model') == 'stock.immediate.transfer':
                        wizard = self.env['stock.immediate.transfer'].browse(
                            res.get('res_id'))
                        wizard.process()
                        return True
                return res
            except Exception:
                pass
        return True

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

    def _prepare_picking(self, move, picking_type_id):
        partner = self.knk_purchase_order_id.partner_id
        location_id = picking_type_id.default_location_src_id.id
        location_dest_id = partner.property_stock_supplier.id
        return {
            'picking_type_id': picking_type_id.id,
            'partner_id': partner.id,
            'date': self.date_of_return,
            'location_dest_id': location_dest_id,
            'location_id': location_id,
            'company_id': self.knk_purchase_order_id.company_id.id,
            'move_type': 'direct'
        }

    def _prepare_stock_moves(self, move, line, picking_type_id, picking, purchase_val_id):
        res = []
        partner = self.knk_purchase_order_id.partner_id
        location_id = picking_type_id.default_location_src_id.id
        location_dest_id = partner.property_stock_supplier.id
        template = {
            'name': line.knk_product_id.name,
            'product_id': line.knk_product_id.id,
            'product_uom': line.knk_product_id.uom_id.id,
            'product_uom_qty': line.knk_product_qty,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
            'picking_id': picking.id,
            'partner_id': partner.id,
            'state': 'draft',
            'purchase_line_id': purchase_val_id,
            'company_id': self.knk_purchase_order_id.company_id.id,
            'picking_type_id': picking_type_id.id,
            'route_ids': picking_type_id.warehouse_id and [
                (6, 0, [
                    x.id for x in picking_type_id.warehouse_id.route_ids])] or
            [],
            'warehouse_id': picking_type_id.warehouse_id.id,
        }
        res.append(template)
        return res

    def process(self, picking):
        # If still in draft => confirm and assign
        if picking.state == 'draft':
            picking.action_confirm()
            if picking.state != 'assigned':
                picking.action_assign()
                if picking.state != 'assigned':
                    raise UserError(
                        _("Could not reserve all requested products. Please use the \
                            'Mark as Todo\
                            ' button to handle the reservation manually."))
        for move in picking.move_ids.filtered(
                lambda m: m.state not in ['done', 'cancel']):
            for move_line in move.move_line_ids:
                move_line.qty_done = move_line.reserved_uom_qty
        picking.state = 'done'
        return True


class PurchaseOrderReturnLine(models.Model):
    _name = 'purchase.order.return.line'
    _description = "Returns lines for purchase order"

    knk_purchase_return_id = fields.Many2one('purchase.order.return')
    knk_product_id = fields.Many2one('product.product',
                                     string="Product",
                                     required="True")
    knk_received_qty = fields.Float(string="Received", readonly=True)
    knk_product_qty = fields.Float(string="Quantity")
    reason_to_return = fields.Char(string="Reason")


    

