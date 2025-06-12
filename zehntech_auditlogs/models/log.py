from odoo import _, api, fields, models
from odoo.exceptions import UserError 


class AuditlogLog(models.Model):
    _name = "auditlog.log"
    _description = "Auditlog - Log"
    _order = "create_date desc"

    name = fields.Char("Resource Name", size=64, help="The name of the resource being logged (e.g., model name or resource identifier).")
    model_id = fields.Many2one("ir.model", string="Model", index=True, ondelete="set null", help="The technical model name associated with the resource.")
    model_name = fields.Char(readonly=True, help="The name of the model associated with the resource.")
    model_model = fields.Char(string="Technical Model Name", readonly=True, help="The technical model name associated with the resource.")
    res_id = fields.Integer("Resource ID", help="The ID of the specific resource instance being logged.")
    user_id = fields.Many2one("res.users", string="User", help="The user who triggered or is associated with this log entry.")
    method = fields.Char(size=64)
    line_ids = fields.One2many("auditlog.log.line", "log_id", string="Fields updated",  help="The specific fields that were updated or changed as part of this log entry.")
    http_session_id = fields.Many2one("auditlog.http.session", string="Session", index=True, help="The HTTP session associated with this log entry.")
    http_request_id = fields.Many2one("auditlog.http.request", string="HTTP Request", index=True, help="The specific HTTP request associated with this log entry.")
    log_type = fields.Selection([("full", "Full log"), ("fast", "Fast log")], string="Type",  help="The type of log: 'Full log' captures all details, 'Fast log' captures basic details.")
    methods = fields.Char(string='Methods', compute="_compute_methods", store=False, help="The method or action that triggered this log entry.")

    @api.depends("method")
    def _compute_methods(self):
        translation_dict = {
            "create": _("create"),
            "read": _("read"),
            "write": _("write"),
            "unlink": _("delete"),
        }
        for record in self:
            record.methods = translation_dict.get(record.method, record.method)
            
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("model_id"):
                raise UserError(_("No model defined to create log."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super(AuditlogLog, self).create(vals_list)

    def write(self, vals):
        if "model_id" in vals:
            if not vals["model_id"]:
                raise UserError(_("The field 'model_id' cannot be empty."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super(AuditlogLog, self).write(vals)
    

