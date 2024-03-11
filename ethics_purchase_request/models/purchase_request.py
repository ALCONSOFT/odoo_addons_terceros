# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import time


class PurchaseRequest(models.Model):
    _name = "purchase.request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Purchase Request"


    name = fields.Char('Purchase Request', index=True, copy=False, default='New')
    employee_id = fields.Many2one('hr.employee', track_visibility="onchange", copy=False, default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', track_visibility="onchange", copy=False)
    request_responsible = fields.Many2one('hr.employee', track_visibility="onchange", copy=False)
    request_date = fields.Date(track_visibility="onchange", default=lambda self: fields.Date.today())
    company_id = fields.Many2one('res.company', track_visibility="onchange", default=lambda self: self.env.company)
    priority = fields.Selection([('0', 'Very Low'), ('1', 'Low'), ('2', 'Normal'), ('3', 'High')], string='Priority', track_visibility="onchange")
    source_document = fields.Char(help='Reference of back purchase request.')
    pr_lines = fields.One2many('purchase.request.line', 'pr_id')
    description = fields.Text()
    pr_reject_reason_id = fields.Many2one("pr.reject.reason",
        string= "Rejection Reason",
        help="This field display reason of PR rejection")
    state = fields.Selection([('draft', 'Draft'),('waiting_for_verifier', 'Waiting For Verifier'),
        ('waiting_for_approver', 'Waiting For Approver'), ('confirm', 'Confirm'), ('cancel', 'Cancelled')], string="Status", default='draft', track_visibility="onchange")
    purchase_ids = fields.Many2many(
        'purchase.order', 'ethics_purchase_request_rel', 'request_id', 'purchase_id', string="Purchase Orders")
    purchase_count = fields.Integer(
        compute="_compute_purchase", string='Purchase Count', copy=False, default=0, store=True)

    @api.depends('purchase_ids')
    def _compute_purchase(self):
        for pr in self:
            if pr.purchase_ids:
                pr.purchase_count = len(pr.purchase_ids.ids)

    @api.onchange('employee_id')
    def _onchange_employee(self):
        parent = self.employee_id.sudo().parent_id
        if self.employee_id and parent:
            self.request_responsible = parent.id
        if self.employee_id and self.employee_id.department_id:
            self.department_id = self.employee_id.department_id.id

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            seq_date = None
            if 'request_date' in vals:
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['request_date']))
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request', sequence_date=seq_date) or '/'
        return super(PurchaseRequest, self).create(vals)

    def create_rfq(self):
        purchase_dict = {}
        purchase_orders = []
        for line in self.pr_lines.filtered(lambda l:l.vendor_ids):
            print("----------------line.vendor_ids----------",line.vendor_ids)
            for vendor in line.vendor_ids:
                print("=======IF==not vendor===purchase_dict====")
                if vendor not in purchase_dict:
                    print("=======IF not=====purchase_dict====",vendor,purchase_dict)
                    purchase_dict.update({vendor: []})
                if purchase_dict:
                    print("=======IF=====purchase_dict====",purchase_dict)
                    purchase_dict[vendor].append((0, 0, {'product_id': line.product_id.id, 'name': line.product_id.name, 'product_qty': line.product_qty, 'product_uom': line.product_uom.id, 'price_unit': 0.0, 'display_type': False, 'date_planned': time.strftime('%Y-%m-%d')}))
        for vendor,lines in purchase_dict.items():
            purchase_id = self.env['purchase.order'].create({
                'partner_id': vendor.id,
                'pr_ref_id': self.id,
                'order_line': lines,
                })
            purchase_orders.append(purchase_id.id)
        self.update({'purchase_ids': [(6, 0, purchase_orders)]})
        self.state = 'confirm'
        return True


    def action_submit_for_verifier(self):
        self.state = 'waiting_for_verifier'

    def action_submit_for_approver(self):
        self.state = 'waiting_for_approver'

    def reject_verifier_pr(self):
        for pr in self:
            pr.write({'state': 'draft'})

    def reject_approver_pr(self):
        view = self.env.ref('ethics_purchase_request.view_add_pr_cancel_reason_form')
        return {
            'name': ('Add Reason'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'add.pr.reason',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'type': 'ir.actions.act_window',
            'target':'new'
        }

    def action_confirm(self):
        if any(line.product_qty == 0 for line in self.pr_lines):
            raise UserError(_("Can you please set product qty."))
        if all(line.vendor_ids for line in self.pr_lines):
            self.create_rfq()
        else:
            view = self.env.ref('ethics_purchase_request.view_back_purchase_request_form')
            wiz_lines = [(0, 0,
                         {'product_id': line.product_id.id,
                          'name': line.product_id.name,
                          'account_analytic_id': line.account_analytic_id.id,
                          'product_qty': line.product_qty,
                          'product_uom': line.product_uom.id})
                         for line in self.pr_lines.filtered(lambda l: not l.vendor_ids and l.product_qty >= 1)]

            return {'name': _('Create Back Purchase Request'),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'views': [(view.id, 'form')],
                    'view_id': view.id,
                    'res_model': 'back.purchase.request',
                    'target': 'new',
                    'context': {
                        'default_pr_id': self.id,
                        'default_employee_id': self.employee_id.id,
                        'default_department_id': self.department_id.id,
                        'default_request_responsible': self.request_responsible.id,
                        'default_request_date': self.request_date,
                        'default_company_id': self.company_id.id,
                        'default_source_document': self.name,
                        'default_back_purchase_request_ids': wiz_lines,
                        }
                    }


class PurchaseRequestLine(models.Model):
    _name = "purchase.request.line"
    _description = "Purchase Request Line"

    pr_id = fields.Many2one('purchase.request')
    product_id = fields.Many2one('product.product')
    name = fields.Char(related="product_id.name", string="Description")
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    product_qty = fields.Float('Quantity', default=1)
    product_uom = fields.Many2one('uom.uom', related='product_id.uom_po_id',
        help="This comes from the product form.")
    vendor_ids = fields.Many2many('res.partner')
