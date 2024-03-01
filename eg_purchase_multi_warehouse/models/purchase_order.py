from odoo import api, fields, models, SUPERUSER_ID, _

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for picking in self.order_line.mapped('picking_type_id'):
            if any([ptype in ['product', 'consu'] for ptype in
                    self.order_line.filtered(lambda s: s.picking_type_id.id == picking.id).mapped(
                            'product_id.type')]):
                res = self._prepare_to_multi_picking(picking)
                created_picking = StockPicking.create(res)
                for line in self.order_line.filtered(lambda s: s.picking_type_id.id == picking.id):
                    moves = line._create_stock_moves(created_picking)
                    moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()
                    seq = 0
                    for move in sorted(moves, key=lambda move: move.date):
                        seq += 5
                        move.sequence = seq
                    moves._action_assign()
                    created_picking.message_post_with_view('mail.message_origin_link',
                                                           values={'self': created_picking,
                                                                   'origin': line.order_id},
                                                           subtype_id=self.env.ref('mail.mt_note').id)
        return True

    @api.model
    def _prepare_to_multi_picking(self, picking_type_id):
        if not self.group_id:
            self.group_id = self.group_id.create({
                'name': self.name,
                'partner_id': self.partner_id.id
            })
        return {
            'picking_type_id': picking_type_id.id,
            'partner_id': self.partner_id.id,
            'user_id': False,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': picking_type_id.default_location_dest_id.id,
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
        }
