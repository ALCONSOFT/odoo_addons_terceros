# -*- coding: utf-8 -*-
# from odoo import http


# class DepositManagement(http.Controller):
#     @http.route('/deposit_management/deposit_management/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/deposit_management/deposit_management/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('deposit_management.listing', {
#             'root': '/deposit_management/deposit_management',
#             'objects': http.request.env['deposit_management.deposit_management'].search([]),
#         })

#     @http.route('/deposit_management/deposit_management/objects/<model("deposit_management.deposit_management"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('deposit_management.object', {
#             'object': obj
#         })
