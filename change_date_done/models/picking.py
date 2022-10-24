# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ChangeDatePickingWizard(models.Model):

	_name = 'change.date.pick'

	scheduled_date = fields.Datetime("Scheduled Date")
	date_done = fields.Datetime("Effective Date")
	
	
	def change_date_picking(self):
		
		print (self)
		print (self._context)
# 		if self.scheduled_date:
# 			for picking in self.env['stock.picking'].search([('id', 'in', self._context['active_ids'])]):
# 				picking.scheduled_date = self.scheduled_date
		if self.date_done:
			for picking in self.env['stock.picking'].search([('id', 'in', self._context['active_ids'])]):
				picking.date_done = self.date_done




	def action_done_picking(self):
		active_ids = self.env.context.get('active_ids')
		if not active_ids:
			return ''

		return {
			'name': 'Change Picking Done / Effective Date',
			'res_model': len(active_ids) == 1 and 'change.date.pick' or 'change.date.pick',
			'view_mode': 'form',
			'view_id': len(active_ids) != 1 and self.env.ref('change_date_done.change_date_pick_form_view').id or self.env.ref('change_date_done.change_date_pick_form_view').id,
			'context': self.env.context,
			'target': 'new',
			'type': 'ir.actions.act_window',
		}
		
		
		
		
		