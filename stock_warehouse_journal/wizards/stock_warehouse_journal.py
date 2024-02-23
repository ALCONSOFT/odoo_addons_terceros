# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import xlsxwriter
import datetime
from io import BytesIO

try:
    from base64 import encodebytes
except ImportError:
    from base64 import encodestring as encodebytes


class StockWarehouseJournal(models.AbstractModel):
    _name = 'report.stock_warehouse_journal.print_stock_warehouse_journal'
    _description = 'Print Stock Warehouse Journal Report'


    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['product.product'].browse(data['ids'])
        location = self.env['stock.location'].browse(data['location_id'])
        location_name = location['display_name']
        date_from = datetime.datetime.strptime(str(data['date_from']), "%Y-%m-%d")
        date_to = datetime.datetime.strptime(str(data['date_to']), "%Y-%m-%d")
        return {
            'ids': docs.ids,
            'model': 'product.product',
            'location_id': data['location_id'],
            'location_name': location_name,
            'date_from': date_from,
            'date_to': date_to,
            'docs': docs,
        }


class StockWarehouseJournalWizard(models.TransientModel):
    _name = 'stock.warehouse.journal.wizard'
    _description = "Stock Warehouse Journal Wizard"
    
    
    @api.constrains('date_from', 'date_to')
    def _check_date(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                if rec.date_from > rec.date_to:
                    raise ValidationError('Date From must be earlier or the same than Date To')
    @api.model
    def _default_date_from(self):
        today = datetime.date.today()
        date_start = today - datetime.timedelta(days=30)
        return date_start
    
    @api.model
    def _default_date_to(self):
        today = datetime.date.today()
        return today                
    
    location_id = fields.Many2one('stock.location', string="Location", required=True)
    date_from = fields.Date(string="Date From", default=_default_date_from, required=True)
    date_to = fields.Date(string="Date To", default=_default_date_to, required=True)
    product_ids = fields.Many2many('product.product', string='Products', domain="[(('type', '=', 'product'))]")
    all_products = fields.Boolean('All Products')
    fileout = fields.Binary('File', readonly=True)
    fileout_filename = fields.Char('Filename', readonly=True)


    def action_stock_warehouse_journal_pdf(self):
        if not self.product_ids and not self.all_products:
            raise ValidationError(_('select a product at least or set All Products indicator either'))
        if self.product_ids and self.all_products:
            raise ValidationError(_('select a product at least or set All Products indicator either'))
        if self.all_products:
            active_ids = self.env['product.product'].search([('type', '=', 'product')]).ids
        else:
            active_ids = self.product_ids.ids                       
        data = { 
            'location_id': self.location_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'ids': active_ids,
        }
        return self.env.ref('stock_warehouse_journal.action_print_stock_warehouse_journal').report_action(active_ids, data=data)

    def action_stock_warehouse_journal_excel(self):
        if not self.product_ids and not self.all_products:
            raise ValidationError(_('select a product at least or set All Products indicator either'))
        if self.product_ids and self.all_products:
            raise ValidationError(_('select a product at least or set All Products indicator either'))
        if self.all_products:
            active_ids = self.env['product.product'].search([('type', '=', 'product')]).ids
        else:
            active_ids = self.product_ids.ids
        data = { 
            'location_id': self.location_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'ids': active_ids,
        }
            
        # Workbook
        file_io = BytesIO()
        workbook = xlsxwriter.Workbook(file_io)
        self.generate_xlsx_report(workbook, data=data)
        workbook.close()
        fout=encodebytes(file_io.getvalue())
        date_string = datetime.date.today().strftime("%Y%m%d")
        report_name = 'Stock Warehouse Journal Report'
        filename = '%s_%s'%(report_name,date_string)
        self.write({'fileout':fout, 'fileout_filename':filename})
        file_io.close()
        filename += '%2Exlsx'
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'web/content/?model='+self._name+'&id='+str(self.id)+'&field=fileout&download=true&filename='+filename,
        }

    def generate_xlsx_report(self, workbook, data=None, objs=None):
        bold = workbook.add_format({'bold': True})
        border_date_right = workbook.add_format({'border':1, 'num_format': 'DD-MM-YYYY', 'bg_color': '#dddddd', 'align': 'right'})
        border_date_ed_center = workbook.add_format({'border':1, 'num_format': 'DD-MM-YYYY', 'bg_color': '#dddddd', 'align': 'center'})
        border_int_right = workbook.add_format({'border':1, 'num_format': '#,##0', 'bg_color': '#dddddd', 'align': 'right'})
        border_int_right_bold = workbook.add_format({'border':1, 'num_format': '#,##0', 'bg_color': '#dddddd', 'align': 'right', 'bold': True})
        border_text_left = workbook.add_format({'border':1, 'bg_color': '#dddddd', 'align': 'left'})
        border_text_center = workbook.add_format({'border':1, 'bg_color': '#dddddd', 'align': 'center'})
        border_text_center_bold = workbook.add_format({'border':1, 'bg_color': '#dddddd', 'align': 'center', 'bold': True})
        header_format_left = workbook.add_format({'bold': True, 'border':1, 'bg_color': '#808080', 'align': 'left'})
        header_format_right = workbook.add_format({'bold': True, 'border':1, 'bg_color': '#808080', 'align': 'right'})
        header_format_center = workbook.add_format({'bold': True, 'border':1, 'bg_color': '#808080', 'align': 'center'})

        def print_initial_stock(row, stock_total):
            sheet.write(row, 0, '', border_date_right) #date-right
            sheet.write(row, 1, '', border_int_right) #text-right
            sheet.write(row, 2, '', border_int_right) #text-right
            sheet.write(row, 3, stock_total, border_int_right_bold) #text-right
            sheet.write(row, 4, '', border_int_right) #text-right
            sheet.write(row, 5, '', border_text_left) #text-left
            sheet.write(row, 6, 'Initial Stock', border_text_center_bold)
            
        def print_final_stock(row, stock_total):
            sheet.write(row, 0, '', border_date_right) #date-right
            sheet.write(row, 1, '', border_int_right) #text-right
            sheet.write(row, 2, '', border_int_right) #text-right
            sheet.write(row, 3, stock_total, border_int_right_bold) #text-right
            sheet.write(row, 4, '', border_int_right) #text-right
            sheet.write(row, 5, '', border_text_left) #text-left
            sheet.write(row, 6, 'Final Stock', border_text_center_bold) 

        
        products = self.env['product.product'].browse(data['ids'])
        location = self.env['stock.location'].browse(data['location_id'])
        location_name = location['display_name']
        locations = self.env['stock.location'].search([('id' ,'child_of', data['location_id'])]).ids
        data['date_from'] = datetime.datetime.strptime(str(data['date_from']), "%Y-%m-%d")
        data['date_to'] = datetime.datetime.strptime(str(data['date_to']), "%Y-%m-%d")
        
        for product in products:
            sheet = workbook.add_worksheet(product.display_name)
            row =0
            sheet.write(row, 0, "Product:", bold)
            sheet.write(row, 1, product.display_name, bold)
            sheet.write(row, 3, "UoM:", bold)
            sheet.write(row, 4, product.uom_id.name, bold)
            row =1
            sheet.write(row, 0, "Location:", bold)
            sheet.write(row, 1, location_name, bold)
            row =2
            sheet.write(row, 0, "Date From:", bold)
            sheet.write(row, 1, data['date_from'].strftime('%d-%m-%Y'), bold)
            row =3
            sheet.write(row, 0, "Tot Receipts:", bold)
            sheet.write(row+1, 0, "Tot Issues:", bold)
            row =5
            date_to_tmp = data['date_to'] + datetime.timedelta(days=1)                    
            sheet.write(row, 0, "Date To:", bold)
            sheet.write(row, 1, data['date_to'].strftime('%d-%m-%Y'), bold)
            row =6
            col = 0
            sheet.write(row, col, 'Date', header_format_left) #text-left
            sheet.set_column('A:A', 10) 
            col += 1
            sheet.write(row, col, 'In', header_format_right) #text-right
            col += 1
            sheet.write(row, col, 'Out', header_format_right) #text-right
            sheet.set_column('B:C', 8)  
            col += 1
            sheet.write(row, col, 'Stock', header_format_right) #text-right
            sheet.set_column('D:D', 10)
            col += 1
            sheet.write(row, col, 'Lot/SN', header_format_left) #text-left                            
            sheet.set_column('E:E', 25) 
            col += 1
            sheet.write(row, col, 'Document Number', header_format_left) #text-left 
            sheet.set_column('F:F', 25) 
            col += 1
            sheet.write(row, col, 'Note', header_format_center) #text-center
            sheet.set_column('G:G', 25)

            stock_initial=stock_total=stock_total_receipts=stock_total_issues=0
            row += 1
            col = 0
                
            for move in product.stock_move_ids:
                for line in move.move_line_ids.filtered(lambda r: r.state == 'done'):
                    if line.location_id.id == location.id or line.location_dest_id.id == location.id:
                        if line.date.strftime('%Y-%m-%d') < data['date_from'].strftime('%Y-%m-%d'):
                            if line.location_dest_id.id == location.id:
                                stock_initial += line.qty_done
                            else:
                                stock_initial -= line.qty_done
            stock_total = stock_initial
            
            for move in product.stock_move_ids:
                for line in move.move_line_ids.filtered(lambda r: r.state == 'done').sorted(key=lambda l: l.date):
                    if line.location_id.id == location.id or line.location_dest_id.id == location.id:
                        if line.date.strftime('%Y-%m-%d') < date_to_tmp.strftime('%Y-%m-%d') and line.date.strftime('%Y-%m-%d') >= data['date_from'].strftime('%Y-%m-%d'):
                            row += 1
                            col = 0
                            
                            sheet.write(row, col, line.date, border_date_right) #date-right
                            col += 1
                            
                            if line.location_dest_id.id == location.id:
                                sheet.write(row, col, line.qty_done, border_int_right) #int-right
                                stock_total = stock_total + line.qty_done
                                stock_total_receipts = stock_total_receipts + line.qty_done
                            else:
                                sheet.write(row, col, '', border_int_right) #int-right
                            col += 1
                            
                            if line.location_id.id == location.id:
                                sheet.write(row, col, line.qty_done, border_int_right) #int-right
                                stock_total = stock_total - line.qty_done
                                stock_total_issues = stock_total_issues - line.qty_done
                            else:
                                sheet.write(row, col, '', border_int_right) #int-right
                            col += 1
                            
                            sheet.write(row, col, stock_total, border_int_right) #int-right
                            col += 1
                            
                            if line.lot_id:
                                sheet.write(row, col, line.lot_id.name, border_text_left) #text-left
                            else:
                                sheet.write(row, col, '', border_text_left) #text-left
                            col += 1                                                
                            
                            if line.picking_id:
                                sheet.write(row, col, line.picking_id.name, border_text_left) #text-left
                            elif line.origin:
                                sheet.write(row, col, line.origin, border_text_left) #text-left
                            else:
                                sheet.write(row, col, '', border_text_left) #text-left
                            col += 1
                            
                            if line.location_dest_id.id == location.id:
                                if line.picking_id and line.picking_id.origin:
                                    if line.picking_id.partner_id.name:
                                        sheet.write(row, col, line.picking_id.partner_id.name, border_text_center) #text-center                                    
                                    else:
                                        sheet.write(row, col, '', border_text_center) #text-center
                                else:
                                    if line.location_id:
                                        if line.location_id.name == 'Inventory adjustment':
                                            sheet.write(row, col, 'Inventory adjustment', border_text_center) #text-center
                                        else:
                                            sheet.write(row, col, '', border_text_center) #text-center
                                    else:
                                        sheet.write(row, col, '', border_text_center) #text-center
                            
                            elif line.location_id.id == location.id:
                                if line.picking_id and line.picking_id.origin:
                                    if line.picking_id.partner_id.name:
                                        sheet.write(row, col, line.picking_id.partner_id.name, border_text_center) #text-center                                    
                                    else:
                                        sheet.write(row, col, '', border_text_center) #text-center
                                else:
                                    if line.location_dest_id:
                                        if line.location_dest_id.name == 'Inventory adjustment':
                                            sheet.write(row, col, 'Inventory adjustment', border_text_center) #text-center
                                        else:
                                            sheet.write(row, col, '', border_text_center) #text-center
                                    else:
                                        sheet.write(row, col, '', border_text_center) #text-center
                            else:
                                sheet.write(row, col, '', border_text_center) #text-center
                    
            print_initial_stock(7, stock_initial)
            print_final_stock(row+1, stock_total)
            sheet.write(3, 2, stock_total_receipts, bold)
            sheet.write(3, 3, product.uom_id.name, bold)
            sheet.write(4, 2, stock_total_issues, bold)
            sheet.write(4, 3, product.uom_id.name, bold)
