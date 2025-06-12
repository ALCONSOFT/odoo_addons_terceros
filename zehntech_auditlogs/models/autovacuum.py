from datetime import datetime, timedelta
from odoo import api, fields, models

class AuditlogAutovacuum(models.TransientModel):
    _name = "auditlog.autovacuum"
    _description = "Auditlog - Delete old logs"

    @api.model
    def autovacuum(self, days, chunk_size=None):
        days = (days > 0) and int(days) or 0
        deadline = datetime.now() - timedelta(days=days)
        data_models = ("auditlog.log", "auditlog.http.request", "auditlog.http.session")
        for data_model in data_models:
            records = self.env[data_model].search(
                [("create_date", "<=", fields.Datetime.to_string(deadline))],
                limit=chunk_size,
                order="create_date asc",
            )
            nb_records = len(records)
            with self.env.norecompute():
                records.unlink()
        return True
