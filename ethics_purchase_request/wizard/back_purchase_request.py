from odoo import api, models, fields, _
from odoo.exceptions import Warning


class BackPurchaseRequest(models.TransientModel):
    _name = 'back.purchase.request'
    _description = 'Back Purchase Request'

    back_purchase_request_ids = fields.One2many(
        'back.purchase.request.line', 'wizard_id')
    pr_id = fields.Many2one('purchase.request')
    employee_id = fields.Many2one('hr.employee', readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    request_responsible = fields.Many2one('hr.employee', readonly=True)
    request_date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    source_document = fields.Char(readonly=True)

    def action_create_pr(self):
        pr_lines = []
        for back_line in self.back_purchase_request_ids:
            pr_lines.append((0, 0,
                {'product_id': back_line.product_id.id,
                 'name': back_line.name,
                 'product_qty': back_line.product_qty,
                 'account_analytic_id': back_line.account_analytic_id.id if back_line.account_analytic_id else False,
                 'product_uom': back_line.product_uom.id}))
        if pr_lines:
            request_id = self.env['purchase.request'].create({
                    'name': 'New',
                    'employee_id': self.pr_id.employee_id.id,
                    'department_id': self.pr_id.department_id.id,
                    'request_responsible': self.pr_id.request_responsible.id,
                    'source_document': self.pr_id.name,
                    'state': 'draft',
                    'priority': self.pr_id.priority,
                    'description': self.pr_id.description,
                    'pr_lines': pr_lines,
                    })
            request_id.action_submit_for_verifier()
            request_id.action_submit_for_approver()
            self.pr_id.create_rfq()

    def action_create_rfq(self):
        self.pr_id.create_rfq()


class BackPurchaseRequestLine(models.TransientModel):
    _name = 'back.purchase.request.line'
    _description = 'Back Purchase Request Line'

    wizard_id = fields.Many2one('back.purchase.request', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    name = fields.Char(readonly=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    product_qty = fields.Float('Quantity', readonly=True)
    product_uom = fields.Many2one('uom.uom', readonly=True)
