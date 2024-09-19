from odoo import http
from odoo.http import request
import io
import xlsxwriter

class PettyCashReportController(http.Controller):

    @http.route('/petty_cash/export/excel', type='http', auth="user", csrf=False)
    def export_petty_cash_to_excel(self, **kwargs):
        # Recuperar los datos que necesitas exportar, ejemplo de un modelo Petty Cash
        petty_cash_id = kwargs.get('id')
        petty_cash_record = request.env['your.model.pettycash'].browse(int(petty_cash_id))

        # Crear archivo Excel en memoria
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet()

        # Formato de encabezado
        header_format = workbook.add_format({'bold': True, 'bg_color': '#F9DA04', 'border': 1})

        # Escribir encabezados
        headers = ['Date', 'Description', 'Particulars', 'Supplier', 'Invoice No', 'Analytic Account', 'Invoice Amount', 'Tax Amount', 'Total Amount']
        for col_num, header in enumerate(headers):
            sheet.write(0, col_num, header, header_format)

        # Escribir las líneas de la tabla
        row = 1
        for line in petty_cash_record.expense_lines:
            sheet.write(row, 0, line.date_expense)
            sheet.write(row, 1, line.note_expense)
            sheet.write(row, 2, line.product_id.name)
            sheet.write(row, 3, line.supplier_id.name)
            sheet.write(row, 4, line.invoice_number)
            sheet.write(row, 5, line.analytic_account_id.name)
            sheet.write(row, 6, line.amount - line.tax_amount)
            sheet.write(row, 7, line.tax_amount)
            sheet.write(row, 8, line.amount)
            row += 1

        # Guardar el archivo en memoria
        workbook.close()
        output.seek(0)

        # Enviar el archivo Excel como una respuesta HTTP
        response = request.make_response(
            output.read(),
            headers=[
                ('Content-Disposition', 'attachment; filename="petty_cash_expense.xlsx"'),
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            ]
        )
        output.close()
        return response
