from odoo import models, fields, api, _

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    picking_type_id = fields.Many2one(comodel_name='stock.picking.type',string="Deliver To")