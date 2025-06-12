from odoo import models

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def name_get(self):
        result = []
        for line in self:
            name = f"{line.picking_id.name or ''} - {line.product_id.display_name or ''} - {line.qty_done} {line.product_uom_id.name or ''} ({line.date or ''})"
            result.append((line.id, name))
        return result 