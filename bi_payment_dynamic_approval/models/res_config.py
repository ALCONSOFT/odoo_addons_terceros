# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    dynamic_approval = fields.Boolean(
        string='Dynamic Approval', related='company_id.dynamic_approval', readonly=False)
    approval_type = fields.Selection(related='company_id.approval_type', string='Total Amount', readonly=False)


    @api.onchange('dynamic_approval')
    def _onchange_dynamic_approval(self):
        if not self.dynamic_approval:
            self.approval_type = False



class Company_Inherit(models.Model):
    _inherit = 'res.company'

    approval_type = fields.Selection(string='Approval Based On', selection=[('total', 'Total Amount'),('before_tax_amount', 'Untaxed Amounts')])
    dynamic_approval = fields.Boolean(string='Dynamic Approval', default=False)

  