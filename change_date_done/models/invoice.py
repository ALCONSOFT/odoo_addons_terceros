# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ChangeDateWizard(models.Model):

	_name = 'change.date'

	date_invoice = fields.Date("Invoice Date")
	date_due = fields.Date("Due Date")
	
	
	def change_date_invoice(self):
		
		print (self)
		print (self._context)
		if self.date_invoice:
			for invoice in self.env['account.move'].search([('id', 'in', self._context['active_ids'])]):
				invoice.invoice_date = self.date_invoice
		if self.date_due:
			for invoice in self.env['account.move'].search([('id', 'in', self._context['active_ids'])]):
				invoice.invoice_date_due = self.date_due



	
	
	def action_done_invoice(self):
		active_ids = self.env.context.get('active_ids')
		if not active_ids:
			return ''

		return {
			'name': 'Change Invoice Date / Due Date',
			'res_model': len(active_ids) == 1 and 'change.date' or 'change.date',
			'view_mode': 'form',
			'view_id': len(active_ids) != 1 and self.env.ref('change_date_done.change_date_form_view').id or self.env.ref('change_date_done.change_date_form_view').id,
			'context': self.env.context,
			'target': 'new',
			'type': 'ir.actions.act_window',
		}
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		