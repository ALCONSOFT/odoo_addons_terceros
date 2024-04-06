# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

from odoo import fields, models


class ApprovalRole(models.Model):
    _name = 'approval.role'
    _description = 'Approval Role'

    name = fields.Char(required=True)


class ApprovalCategory(models.Model):
    _name = 'approval.categ'
    _description = 'Approval Category'

    name = fields.Char(required=True)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    approval_role = fields.Many2many('approval.role', 'approval_role_hr_employee_rel', 'approval_role_id', 'hr_employee_id', string='Approval Role')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    approval_category = fields.Many2one('approval.categ', string='Approval Category')
