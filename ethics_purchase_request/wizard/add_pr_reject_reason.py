# -*- coding: utf-8 -*-
from odoo import api,fields,models,_


class AddPRRejectReason(models.TransientModel):
    _name="add.pr.reason"
    _description = "Add PR Reason"

    pr_reject_reason_id = fields.Many2one("pr.reject.reason",
        string= "PR Rejection Reason",
        required =True,
        help="This field display reason of PR rejection")

    # For adding the reason of rejection PR on purchase request
    def reject_pr(self):
        if self.env.context.get('active_model') == 'purchase.request':
            active_model_id = self.env.context.get('active_id')
            purchase_request_obj = self.env['purchase.request'].search([('id','=', active_model_id)])
            purchase_request_obj.write({
                'pr_reject_reason_id': self.pr_reject_reason_id.id,
                'state':'cancel'})
            employee_name = purchase_request_obj.employee_id.sudo().name
            msg = """ Dear """ + employee_name + """,
                    <br />
                    Your purchase request is rejected because of """ + self.pr_reject_reason_id.name
            purchase_request_obj.message_post(body=msg)
