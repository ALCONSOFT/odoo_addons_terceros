# -*- coding: utf-8 -*-
from odoo import api,fields,models,_


class PRRejectReason(models.Model):
    _name = "pr.reject.reason"
    _description = "PR Reject Reason"

    name = fields.Char(string='Reject Reason', help="For adding the reason for PR Rejection.")
