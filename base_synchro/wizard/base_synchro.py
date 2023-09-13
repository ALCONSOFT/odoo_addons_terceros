# See LICENSE file for full copyright and licensing details.
from datetime import datetime
import pytz
from ast import For
import base64
import datetime
import logging
import socket
from ssl import AlertDescription
import threading
import time
from xmlrpc.client import ServerProxy
from odoo import api, fields, models
from odoo import tools
from odoo.exceptions import ValidationError
from odoo.tools.translate import _
from odoo.tools import format_datetime
import xmlrpc.client

_logger = logging.getLogger(__name__)


class RPCProxyOne(object):
    def __init__(self, server, ressource):
        """Class to store one RPC proxy server."""
        self.server = server
        local_url = "http://%s:%d/xmlrpc/common" % (
            server.server_url,
            server.server_port,
        )
        rpc = ServerProxy(local_url)
        self.uid = rpc.login(server.server_db, server.login, server.password)
        local_url = "http://%s:%d/xmlrpc/object" % (
            server.server_url,
            server.server_port,
        )
        self.rpc = ServerProxy(local_url)
        self.ressource = ressource

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.rpc.execute(
            self.server.server_db,
            self.uid,
            self.server.password,
            self.ressource,
            name,
            *args
        )


class RPCProxy(object):
    """Class to store RPC proxy server."""

    def __init__(self, server):
        self.server = server

    def get(self, ressource):
        return RPCProxyOne(self.server, ressource)


class BaseSynchro(models.TransientModel):
    """Base Synchronization."""

    _name = "base.synchro"
    _description = "Base Synchronization"

    @api.depends("server_url")
    def _compute_report_vals(self):
        self.report_total = 0
        self.report_create = 0
        self.report_write = 0

    accion_cierre = fields.Selection([("No","No"),("Si","Si")], default="No")
    fecha_cierre_sync = fields.Datetime("Fecha de Cierre", default=fields.Datetime.now)
    @api.onchange('fecha_cierre_sync')
    def _onchange_fecha_cierre_sync(self):
        # Aquí va la lógica de tu función
        print("__________ON CHANGE FECHA CIERRE SYNC_________")
        self.estado_de_registros_marcados_cerrado = self._get_regs_sin_marcar(self.fecha_cierre_sync)

    server_url = fields.Many2one(
        "base.synchro.server", 
        "Server URL", 
        required=True, 
        default=lambda self: self.env['base.synchro.server'].search([], limit=1)
    )
    user_id = fields.Many2one(
        "res.users", "Send Result To", default=lambda self: self.env.user
    )
    report_total = fields.Integer(compute="_compute_report_vals")
    report_create = fields.Integer(compute="_compute_report_vals")
    report_write = fields.Integer(compute="_compute_report_vals")

    @api.model
    def synchronize(self, server, object):
        pool = self
        sync_ids = []
        pool1 = RPCProxy(server)
        pool2 = pool
        dt = object.synchronize_date
        module = pool1.get("ir.module.module")
        model_obj = object.model_id.model
        module_id = module.search(
            [("name", "ilike", "base_synchro"), ("state", "=", "installed")]
        )
        if not module_id:
            raise ValidationError(
                _(
                    """If your Synchronization direction is/
                          download or both, please install
                          "Multi-DB Synchronization" module in targeted/
                        server!"""
                )
            )
        if object.action in ("d", "b"):
            sync_ids = pool1.get("base.synchro.obj").get_ids(
                model_obj, dt, eval(object.domain), {"action": "d"}
            )

        if object.action in ("u", "b"):
            _logger.debug(
                "Getting ids to synchronize [%s] (%s)",
                object.synchronize_date,
                object.domain,
            )
            sync_ids += pool2.env["base.synchro.obj"].get_ids(
                model_obj, dt, eval(object.domain), {"action": "u"}
            )
        sorted(sync_ids, key=lambda x: str(x[0]))
        for dt, id, action in sync_ids:
            destination_inverted = False
            if action == "d":
                pool_src = pool1
                pool_dest = pool2
            else:
                pool_src = pool2
                pool_dest = pool1
                destination_inverted = True
            fields = False
            if object.model_id.model == "crm.case.history":
                fields = ["email", "description", "log_id"]
            if not destination_inverted:
                value = pool_src.get(
                    object.model_id.model).read([id], fields)[0]
            else:
                model_obj = pool_src.env[object.model_id.model]
                value = model_obj.browse([id]).read(fields)[0]
            if "create_date" in value:
                del value["create_date"]
            if "write_date" in value:
                del value["write_date"]
            for key, val in value.items():
                if isinstance(val, tuple):
                    value.update({key: val[0]})
            value = self.data_transform(
                pool_src,
                pool_dest,
                object.model_id.model,
                value,
                action,
                destination_inverted,
            )

            id2 = self.get_id(object.id, id, action)

            # Filter fields to not sync
            for field in object.avoid_ids:
                if field.name in value:
                    del value[field.name]
            if id2:
                _logger.debug(
                    "Updating model %s [%d]", object.model_id.name, id2
                )
                if not destination_inverted:
                    model_obj = pool_dest.env[object.model_id.model]
                    model_obj.browse([id2]).write(value)
                else:
                    pool_dest.get(object.model_id.model).write([id2], value)
                self.report_total += 1
                self.report_write += 1
            else:
                _logger.debug("Creating model %s", object.model_id.name)
                if not destination_inverted:
                    if object.model_id.model == "sale.order.line":
                        if value['product_template_id']:
                            value['product_id'] = value['product_template_id']
                            del value['product_template_id']
                            idnew = pool_dest.env[object.model_id.model].create(
                                value)
                            new_id = idnew.id
                        else:
                            idnew = pool_dest.env[object.model_id.model].create(
                                value)
                            new_id = idnew.id
                    elif object.model_id.model == "stock.move.line":
                        a = value.pop('product_qty')
                        b = value.pop('product_uom_qty')
                        idnew = pool_dest.env[object.model_id.model].create(
                            value)
                        idnew.write({
                            'product_uom_qty': b
                        })
                        new_id = idnew.id
                    else:
                        idnew = pool_dest.env[object.model_id.model].create(
                            value)
                        new_id = idnew.id
                else:
                    idnew = pool_dest.get(object.model_id.model).create(value)
                    new_id = idnew
                self.env["base.synchro.obj.line"].create(
                    {
                        "obj_id": object.id,
                        "local_id": (action == "u") and id or new_id,
                        "remote_id": (action == "d") and id or new_id,
                    }
                )
                self.report_total += 1
                self.report_create += 1
        return True

    @api.model
    def get_id(self, object_id, id, action):
        synchro_line_obj = self.env["base.synchro.obj.line"]
        field_src = (action == "u") and "local_id" or "remote_id"
        field_dest = (action == "d") and "local_id" or "remote_id"
        rec_id = synchro_line_obj.search(
            [("obj_id", "=", object_id), (field_src, "=", id)]
        )
        result = False
        if rec_id:
            result = synchro_line_obj.browse([rec_id[0].id]).read([field_dest])
            if result:
                result = result[0][field_dest]
        return result

    @api.model
    def relation_transform(
        self,
        pool_src,
        pool_dest,
        obj_model,
        res_id,
        action,
        destination_inverted,
    ):

        if not res_id:
            return False
        _logger.debug("Relation transform")
        self._cr.execute(
            """select o.id from base_synchro_obj o left join
                        ir_model m on (o.model_id =m.id) where
                        m.model=%s and o.active""",
            (obj_model,),
        )
        obj = self._cr.fetchone()
        result = False
        if obj:
            result = self.get_id(obj[0], res_id, action)
            _logger.debug(
                "Relation object already synchronized. Getting id%s", result
            )
            if obj_model == "stock.location":
                names = pool_src.get(obj_model).name_get([res_id])[0][1]
                res = pool_dest.env[obj_model]._name_search(names, [], "like")
                from_clause, where_clause, where_clause_params = res.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                query_str = 'SELECT "%s".id FROM ' % pool_dest.env[obj_model]._table + \
                    from_clause + where_str
                order_by = pool_dest.env[obj_model]._generate_order_by(
                    None, query_str)
                query_str = query_str + order_by
                pool_dest.env[obj_model]._cr.execute(
                    query_str, where_clause_params)
                res1 = self._cr.fetchall()
                res = [ls[0] for ls in res1]
                result = res[0]
            if obj_model == "stock.picking.type":
                names = pool_src.get(obj_model).name_get([res_id])[0][1]
                name = names.split(':')[0].strip()
                res = pool_dest.env[obj_model]._name_search(name, [], "like")
                from_clause, where_clause, where_clause_params = res.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                query_str = 'SELECT "%s".id FROM ' % pool_dest.env[obj_model]._table + \
                    from_clause + where_str
                order_by = pool_dest.env[obj_model]._generate_order_by(
                    None, query_str)
                query_str = query_str + order_by
                pool_dest.env[obj_model]._cr.execute(
                    query_str, where_clause_params)
                res1 = self._cr.fetchone()
                result = res1
        else:
            _logger.debug(
                """Relation object not synchronized. Searching/
             by name_get and name_search"""
            )
            report = []

            if not destination_inverted:
                if obj_model == "res.country.state":
                    names = pool_src.get(obj_model).name_get([res_id])[0][1]
                    name = names.split("(")[0].strip()
                    res = pool_dest.env[obj_model]._name_search(
                        name, [], "like")
                    res = [res]
                elif obj_model == "res.country":
                    names = pool_src.get(obj_model).name_get([res_id])[0][1]
                    res = pool_dest.env[obj_model]._name_search(names, [], "=")
                    res = [[res[0]]]
                else:
                    names = pool_src.get(obj_model).name_get([res_id])[0][1]
                    res = pool_dest.env[obj_model].name_search(
                        names, [], "like")
            else:
                model_obj = pool_src.env[obj_model]
                names = model_obj.browse([res_id]).name_get()[0][1]
                res = pool_dest.get(obj_model).name_search(names, [], "like")
            _logger.debug("name_get in src: %s", names)
            _logger.debug("name_search in dest: %s", res)
            if res:
                result = res[0][0]
            else:
                _logger.warning(
                    """Record '%s' on relation %s not found, set/
                                to null.""",
                    names,
                    obj_model,
                )
                _logger.warning(
                    """You should consider synchronize this/
                model '%s""",
                    obj_model,
                )
                report.append(
                    """WARNING: Record "%s" on relation %s not/
                    found, set to null."""
                    % (names, obj_model)
                )
        return result

    @api.model
    def data_transform(
        self,
        pool_src,
        pool_dest,
        obj,
        data,
        action=None,
        destination_inverted=False,
    ):
        if action is None:
            action = {}
        if not destination_inverted:
            fields = pool_src.get(obj).fields_get()
        else:
            fields = pool_src.env[obj].fields_get()
        _logger.debug("Transforming data")
        for f in fields:
            ftype = fields[f]["type"]
            if ftype in ("function", "one2many", "one2one"):
                _logger.debug("Field %s of type %s, discarded.", f, ftype)
                del data[f]
            elif ftype == "many2one":
                _logger.debug("Field %s is many2one", f)
                if (isinstance(data[f], list)) and data[f]:
                    fdata = data[f][0]
                else:
                    fdata = data[f]

                df = self.relation_transform(
                    pool_src,
                    pool_dest,
                    fields[f]["relation"],
                    fdata,
                    action,
                    destination_inverted,
                )
                if obj == "stock.picking":
                    data[f] = df
                    if not data[f]:
                        del data[f]
                else:
                    data[f] = df
                    if not data[f]:
                        del data[f]

            elif ftype == "many2many":
                res = map(
                    lambda x: self.relation_transform(
                        pool_src,
                        pool_dest,
                        fields[f]["relation"],
                        x,
                        action,
                        destination_inverted,
                    ),
                    data[f],
                )
                data[f] = [(6, 0, [x for x in res if x])]
        del data["id"]
        return data

    def upload_download(self):
        self.ensure_one()
        report = []
        start_date = fields.Datetime.now()
        timezone = self._context.get("tz", "UTC")
        start_date = format_datetime(
            self.env, start_date, timezone, dt_format=False
        )
        server = self.server_url
        for obj_rec in server.obj_ids:
            _logger.debug("Start synchro of %s", obj_rec.name)
            dt = fields.Datetime.now()
            self.synchronize(server, obj_rec)
            if obj_rec.action == "b":
                time.sleep(1)
                dt = fields.Datetime.now()
            obj_rec.write({"synchronize_date": dt})
        end_date = fields.Datetime.now()
        end_date = format_datetime(
            self.env, end_date, timezone, dt_format=False
        )
        # Creating res.request for summary results
        if self.user_id:
            request = self.env["res.request"]
            if not report:
                report.append("No exception.")
            summary = """Here is the synchronization report:

     Synchronization started: %s
     Synchronization finished: %s

     Synchronized records: %d
     Records updated: %d
     Records created: %d

     Exceptions:
        """ % (
                start_date,
                end_date,
                self.report_total,
                self.report_write,
                self.report_create,
            )
            summary += "\n".join(report)
            request.create(
                {
                    "name": "Synchronization report",
                    "act_from": self.env.user.id,
                    "date": fields.Datetime.now(),
                    "act_to": self.user_id.id,
                    "body": summary,
                }
            )
            return {}

    def upload_download_multi_thread(self):
        threaded_synchronization = threading.Thread(
            target=self.upload_download()
        )
        threaded_synchronization.run()
        id2 = self.env.ref("base_synchro.view_base_synchro_finish").id
        return {
            "binding_view_types": "form",
            "view_mode": "form",
            "res_model": "base.synchro",
            "views": [(id2, "form")],
            "view_id": False,
            "type": "ir.actions.act_window",
            "target": "new",
        }

    def action_down_users(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model res_users on cloud
        filtro = [[['active', '=', True]]]
        count_users = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'res.users', 'search_count', filtro)
        list_users = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.users', 'search_read', filtro, {
                                             'fields': ['name', 'login', 'password', 'company_id']})
        for n in list_users:
            print(n)
            # Buscar si el id o llave priamria existe en res.users
            search_user = self.env['res.users'].search(
                [('login', '=', n['login'])])
            # Guardar registro list_users[n] en res.users local
            if search_user.active == False:
                new_user = self.env['res.users'].create(
                    {'name': n['name'], 'login': n['login'], 'password': n['password'], 'company_id': n['company_id'][0]})
        # except Exception:
        #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return

    def action_down_partners(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model res_partener
        filtro = [[['active', '=', True],]]
        count_partners = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'res.partner', 'search_count', filtro)
        list_partners = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.partner', 'search_read', filtro, {'fields': ['name',
                                                                                                                       'company_id',
                                                                                                                       'display_name',
                                                                                                                       'ref',
                                                                                                                       'active',
                                                                                                                       'type',
                                                                                                                       'is_company',
                                                                                                                       'company_name',
                                                                                                                       'supplier_rank']})
        for n in list_partners:
            print(n)
            lc_mens = n['name']
            # Buscar si el id o llave primaria existe en res.partner.  si tiene ref hacer la busqueda.
            if (n['ref'] != False):
                search_partner = self.env['res.partner'].search(
                    [('ref', '=', n['ref'])])
                # Guardar registro list_partner[n] en res.partner local
                if not n['company_id'] == 303:
                    ln_cia = 1
                else:
                    ln_cia = n['company_id'][0]
                if search_partner.active == False:
                    new_partner = self.env['res.partner'].create({'name': n['name'],
                                                                  'display_name': n['display_name'],
                                                                  'ref': n['ref'],
                                                                  'company_id': ln_cia,
                                                                  'active': n['active'],
                                                                  'type': n['type'],
                                                                  'is_company': n['is_company'],
                                                                  'company_name': n['company_name'],
                                                                  'supplier_rank': n['supplier_rank']})
            else:
                print("Partner name no tiene codigo de referencia: " + lc_mens)
            # except Exception:
            #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return

    def action_down_products(self):
        # self.action_down_uoms() ; da muchos problemas con los tipos de unidades de medidas
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model product_template
        filtro = [[['active', '=', True],]]
        count_producttemplate = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'product.template', 'search_count', filtro)
        list_producttemplate = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.template', 'search_read', filtro, {'fields': ['name',
                                                                                                                                   'description',
                                                                                                                                   'type',
                                                                                                                                   'categ_id',
                                                                                                                                   'sale_ok',
                                                                                                                                   'purchase_ok',
                                                                                                                                   'uom_id',
                                                                                                                                   'active',
                                                                                                                                   'default_code',
                                                                                                                                   'uom_po_id',
                                                                                                                                   'tracking'],
                                                                                                                        'order': 'id'})
        for n in list_producttemplate:
            print(n)
            reg_pt = self.action_down_product_template(n)
            # ln_idpt = reg_pt.id
            # ln_idpp = self.action_down_product_quant(n, ln_idpt)
        return

    def action_down_stock_quant(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model stock.quant
        filtro = [[]]
        count_stockquant = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'stock.quant', 'search_count', filtro)
        list_stockquant = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.quant', 'search_read', filtro, {'fields': ['id',
                                                                                                                         'product_id',
                                                                                                                         'company_id',
                                                                                                                         'location_id',
                                                                                                                         'lot_id',
                                                                                                                         'package_id',
                                                                                                                         'owner_id',
                                                                                                                         'quantity',
                                                                                                                         'reserved_quantity',
                                                                                                                         'in_date'],
                                                                                                              'order': 'id'
                                                                                                              })
        listsearch_product_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.product',
                                                          'search_read',
                                                          [()],
                                                          {'fields': ['id', 'default_code'], 'order': 'id'})
        listsearch_location_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location',
                                                           'search_read',
                                                           [()],
                                                           {'fields': ['id', 'name', 'parent_path'], 'order': 'id'})
        for n in list_stockquant:
            print("---------------------------------------stock quant------------------------------------------------------------")
            print(n)
            lc_mens = n['product_id'][1]
            # product
            product_id_nube_quant = n['product_id'][0]
            lc_defaul_code = self.search_en_listsearched(
                'id', product_id_nube_quant, listsearch_product_nube, 'default_code')
            search_product_local = self.env['product.product'].search(
                [('default_code', '=', lc_defaul_code)])
            # location
            location_id_nube_quant = n['location_id'][0]
            lc_location_parent_path = self.search_en_listsearched(
                'id', location_id_nube_quant, listsearch_location_nube, 'parent_path')
            search_location_local = self.env['stock.location'].search(
                [('parent_path', '=', lc_location_parent_path)])
            # lot
            lot_id_nube_quant = self.norma_false(n['lot_id'])
            # buscar en tabla quant local
            if search_product_local.id == False or search_location_local.id == False:
                continue
            else:
                lc_filtro = [('product_id', '=', search_product_local.id),
                             ('location_id', '=', search_location_local.id),
                             ('lot_id', '=', lot_id_nube_quant)]
            # Buscar si existe: id
            search_stockquant = self.env['stock.quant'].search(lc_filtro)
            if search_stockquant.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("----------------Actualizando-----------------")
                update_stockquant = search_stockquant.write(
                    {
                        'product_id': search_product_local.id,
                        'company_id': self.norma_false(n['company_id']),
                        'location_id': search_location_local.id,
                        'lot_id': lot_id_nube_quant,
                        'package_id': n['package_id'],
                        'owner_id': n['owner_id'],
                        'quantity': n['quantity'],
                        'reserved_quantity': n['reserved_quantity'],
                        'in_date': n['in_date']
                    }
                )
            else:
                # El id no existe asi que se creara
                print("----------------Creando------------------------")
                new_stockquant = self.env['stock.quant'].create({
                    'product_id': search_product_local.id,
                    'company_id': self.norma_false(n['company_id']),
                    'location_id': search_location_local.id,
                    'lot_id': lot_id_nube_quant,
                    'package_id': n['package_id'],
                    'owner_id': n['owner_id'],
                    'quantity': n['quantity'],
                    'reserved_quantity': n['reserved_quantity'],
                    'in_date': n['in_date']
                }
                )
                print(new_stockquant)
        return

    def action_down_product_template(self, n):
        lc_mens = n['name']
        print("+++++++++++++++++++++++++++++  PRODUCT TEMPLATE  ++++++++++++++++++++++++")
        # Buscar si el id o llave primaria existe en res.partner. Si tiene default_code hacer la busqueda
        if (n['default_code'] != False):
            search_producttemplate = self.env['product.template'].search(
                [('default_code', '=', n['default_code'])])
            # Decidi Normalizar las unidades de medida a Unit id=1 de todos los productos
            # Guardar registro list_producttemplate[n] en product_template local
            if search_producttemplate.active == False:
                print(
                    ">>>>>>>>>>>>> - - - - - NO EXISTE EN PRODUCT TEMPLATE - - - - - - - - >>>>>>>>>")
                new_producttemplate = self.env['product.template'].create({'name': n['name'],
                                                                           'description': n['description'],
                                                                           'type': n['type'],
                                                                           'categ_id': n['categ_id'][0],
                                                                           'sale_ok': n['sale_ok'],
                                                                           'purchase_ok': n['purchase_ok'],
                                                                           'uom_id': 1,
                                                                           'active': n['active'],
                                                                           'default_code': n['default_code'],
                                                                           'uom_po_id': 1,
                                                                           'tracking': n['tracking']})
            else:
                print(">>>>>>>>>> - - Ya existe en product.template *-*-*-*-*-* ")
                new_producttemplate = False
        else:
            print(
                ">>>>>>>>>>>>> -   Product Template name no tiene codigo de referencia: " + lc_mens)
            new_producttemplate = False
        # Guardar registro en product_product
        # except Exception:
        #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return new_producttemplate

    def action_down_stock_warehouse(self):
        # crear la conexion con el servidor en la url de la nube
        print("-------------- Empezado funcion: down_stock_warehouse() -------------")
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("Conexion en down_stock_warehouse() - common version: ",
                  common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model sotck.warehouse
        filtro = [[['active', '=', True],]]
        count_stockwarehouse = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'stock.warehouse', 'search_count', filtro)
        list_stockwarehouse = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.warehouse', 'search_read', filtro, {'fields': ['name',
                                                                                                                                 'company_id',
                                                                                                                                 'partner_id',
                                                                                                                                 'view_location_id',
                                                                                                                                 'lot_stock_id',
                                                                                                                                 'code',
                                                                                                                                 'reception_steps',
                                                                                                                                 'active',
                                                                                                                                 'delivery_steps',
                                                                                                                                 'wh_input_stock_loc_id',
                                                                                                                                 'wh_qc_stock_loc_id',
                                                                                                                                 'wh_output_stock_loc_id',
                                                                                                                                 'wh_pack_stock_loc_id',
                                                                                                                                 'mto_pull_id',
                                                                                                                                 'pick_type_id',
                                                                                                                                 'pack_type_id',
                                                                                                                                 'out_type_id',
                                                                                                                                 'in_type_id',
                                                                                                                                 'int_type_id',
                                                                                                                                 'crossdock_route_id',
                                                                                                                                 'reception_route_id',
                                                                                                                                 'delivery_route_id',
                                                                                                                                 'sequence'
                                                                                                                                 ],
                                                                                                                      'order': 'id'})
        for n in list_stockwarehouse:
            print(" - Empezando a recorrer la lista de Warehouses. . . ", n)
            lc_mens = n['name']
            # Buscar si el id o llave primaria existe en stock.warehouse.  si tiene "code" hacer la busqueda.
            # CONDICION ESPECIAL: asumiremos que WH=0001.  Por lo tanto si el code de la bodega local = "WH";
            #   solo cambiaremos los campos: NAME y CODE
            if (n['code'] != False):
                codigo_bodega_nube = n['code']
                codigo_bodega_local = self.env['stock.warehouse'].search(
                    [('code', '=', 'WH')])
                print(" - - Codigo Bodega Nube de Referencia : ",
                      codigo_bodega_nube)
                if codigo_bodega_local.id != False:
                    print(" - - - [w1]")
                    # Si el codigo_bodega_local no es False: entonces existe WH
                    # y cambiaremos name y code:  Se ha asumido que los demas paramentros son iguales en ambas bases de datos
                    search_stockwarehouse = self.env['stock.warehouse'].search(
                        [('code', '=', 'WH')])
                    # Actualizar registro list_stockwarehouse[n] en stock.warehouse local
                    new_stockwarehouse = search_stockwarehouse.write({'name': n['name'],
                                                                      'code': n['code']})
                else:
                    print(" - - - [w2]")
                    # Si no entonces: no existe WH y puede ser que code="0001"
                    if codigo_bodega_nube == '0001':
                        print(" - - - - [w2-1]")
                        # actualizar todos los parametros de la bodega: 001
                        search_stockwarehouse = self.env['stock.warehouse'].search(
                            [('code', '=', n['code'])])
                        new_stockwarehouse = search_stockwarehouse.write({'name': n['name'],
                                                                          'partner_id': n['partner_id'][0],
                                                                          'view_location_id': n['view_location_id'][0],
                                                                          'lot_stock_id': n['lot_stock_id'][0],
                                                                          'reception_steps': n['reception_steps'],
                                                                          'active': n['active'],
                                                                          'delivery_steps': n['delivery_steps'],
                                                                          'wh_input_stock_loc_id': n['wh_input_stock_loc_id'][0],
                                                                          'wh_qc_stock_loc_id': n['wh_qc_stock_loc_id'][0],
                                                                          'wh_output_stock_loc_id': n['wh_output_stock_loc_id'][0],
                                                                          'wh_pack_stock_loc_id': n['wh_pack_stock_loc_id'][0],
                                                                          'mto_pull_id': n['mto_pull_id'][0],
                                                                          'pick_type_id': n['pick_type_id'][0],
                                                                          'pack_type_id': n['pack_type_id'][0],
                                                                          'out_type_id': n['out_type_id'][0],
                                                                          'in_type_id': n['in_type_id'][0],
                                                                          'int_type_id': n['int_type_id'][0],
                                                                          'crossdock_route_id': n['crossdock_route_id'][0],
                                                                          'reception_route_id': n['reception_route_id'][0],
                                                                          'delivery_route_id': n['delivery_route_id'][0],
                                                                          'sequence': n['sequence']})
                    else:
                        # La bodega no existe y hay que crearla; pero solo se permite una bodega o warehouse
                        # Pendiente de programacion: Alconsoft 3-nov-2022
                        print(" - - - - [w2-2] --*--")
            else:
                print("Warehouse name no tiene codigo de referencia: " + lc_mens)
            # except Exception:
            #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        print("+++++++++++++++++++++++++++++++ FIN DE WWAREHOUSE ++++++++++++++++++++++++++++++++++++++++++++++++++")
        return

    def action_down_stock_location(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model sotck.location
        filtro = [[]]
        count_stocklocation = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'stock.location', 'search_count', filtro)
        list_stocklocation = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_read', filtro, {'fields': ['id',
                                                                                                                               'name',
                                                                                                                               'complete_name',
                                                                                                                               'active',
                                                                                                                               'usage',
                                                                                                                               'location_id',
                                                                                                                               'comment',
                                                                                                                               'posx',
                                                                                                                               'posy',
                                                                                                                               'posz',
                                                                                                                               'parent_path',
                                                                                                                               'company_id',
                                                                                                                               'scrap_location',
                                                                                                                               'return_location',
                                                                                                                               'removal_strategy_id',
                                                                                                                               'barcode',
                                                                                                                               'valuation_in_account_id',
                                                                                                                               'valuation_out_account_id'],
                                                                                                                    'order': 'id'}
                                                     )
        for n in list_stocklocation:
            print("---------------------------------------stock location------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id'] != False):
                search_stocklocation = self.env['stock.location'].search(
                    [('id', '=', n['id'])])
                if search_stocklocation.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print("----------------Actualizando-----------------")
                    update_stocklocation = search_stocklocation.write(
                        {
                            'name': n['name'],
                            'complete_name': n['complete_name'],
                            'active': n['active'],
                            'usage': n['usage'],
                            'location_id': self.norma_false(n['location_id']),
                            'comment': n['comment'],
                            'posx': n['posx'],
                            'posy': n['posy'],
                            'posz': n['posz'],
                            'parent_path': n['parent_path'],
                            'scrap_location': n['scrap_location'],
                            'return_location': n['return_location'],
                            'removal_strategy_id': self.norma_false(n['removal_strategy_id']),
                            'barcode': n['barcode'],
                            'valuation_in_account_id': self.norma_false(n['valuation_in_account_id']),
                            'valuation_out_account_id': self.norma_false(n['valuation_out_account_id'])
                        }
                    )
                else:
                    # El id no existe asi que se creara
                    print(
                        "----------------Creando-----------------'id':n['id'],")
                    new_stocklocation = self.env['stock.location'].create({
                        'name': n['name'],
                        'complete_name': n['complete_name'],
                        'active': n['active'],
                        'usage': n['usage'],
                        'location_id': self.norma_false(n['location_id']),
                        'company_id': self.norma_false(n['company_id']),
                        'comment': n['comment'],
                        'posx': n['posx'],
                        'posy': n['posy'],
                        'posz': n['posz'],
                        'parent_path': n['parent_path'],
                        'scrap_location': n['scrap_location'],
                        'return_location': n['return_location'],
                        'removal_strategy_id': self.norma_false(n['removal_strategy_id']),
                        'barcode': n['barcode'],
                        'valuation_in_account_id': self.norma_false(n['valuation_in_account_id']),
                        'valuation_out_account_id': self.norma_false(n['valuation_out_account_id'])
                    }
                    )
                    print(new_stocklocation)
        return

    def action_down_stock_picking_type(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model sotck.picking.type
        filtro = [[]]
        count_stockpickingtype = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'stock.picking.type', 'search_count', filtro)
        list_stockpickingtype = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking.type', 'search_read', filtro, {'fields': ['id',
                                                                                                                                      'name',
                                                                                                                                      'color',
                                                                                                                                      'sequence',
                                                                                                                                      'sequence_id',
                                                                                                                                      'sequence_code',
                                                                                                                                      'default_location_src_id',
                                                                                                                                      'default_location_dest_id',
                                                                                                                                      'code',
                                                                                                                                      'return_picking_type_id',
                                                                                                                                      'show_entire_packs',
                                                                                                                                      'warehouse_id',
                                                                                                                                      'active',
                                                                                                                                      'use_create_lots',
                                                                                                                                      'use_existing_lots',
                                                                                                                                      'show_operations',
                                                                                                                                      'show_reserved',
                                                                                                                                      'barcode',
                                                                                                                                      'company_id'],
                                                                                                                           'order': 'id'})
        for n in list_stockpickingtype:
            print("---------------------------------------stock picking type------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id'] != False):
                search_stockpickingtype = self.env['stock.picking.type'].search(
                    [('id', '=', n['id'])])
                if search_stockpickingtype.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print(
                        "--------------actualizando---- 'return_picking_type_id':n['return_picking_type_id'][0],------")
                    update_stockpickingtype = search_stockpickingtype.write(
                        {
                            'name': n['name'],
                            'color': n['color'],
                            'sequence': n['sequence'],
                            'sequence_id': n['sequence_id'][0],
                            'sequence_code': n['sequence_code'],
                            'default_location_src_id': n['default_location_src_id'][0],
                            'default_location_dest_id': n['default_location_dest_id'][0],
                            'code': n['code'],
                            'show_entire_packs': n['show_entire_packs'],
                            'warehouse_id': n['warehouse_id'][0],
                            'active': n['active'],
                            'use_create_lots': n['use_create_lots'],
                            'use_existing_lots': n['use_existing_lots'],
                            'show_operations': n['show_operations'],
                            'show_reserved': n['show_reserved'],
                            'barcode': n['barcode'],
                            'company_id': n['company_id'][0]
                        }
                    )
                else:
                    # De lo contrario id no existe y hay q crear el registro
                    print("------------- Creando -------------------")
                    new_stockpickingtype = self.env['stock.picking.type'].create({'id': n['id'],
                                                                                  'name': n['name'],
                                                                                  'color': n['color'],
                                                                                  'sequence': n['sequence'],
                                                                                  'sequence_id': n['sequence_id'][0],
                                                                                  'sequence_code': n['sequence_code'],
                                                                                  'default_location_src_id': n['default_location_src_id'][0],
                                                                                  'default_location_dest_id': n['default_location_dest_id'][0],
                                                                                  'code': n['code'],
                                                                                  'show_entire_packs': n['show_entire_packs'],
                                                                                  'warehouse_id': n['warehouse_id'][0],
                                                                                  'active': n['active'],
                                                                                  'use_create_lots': n['use_create_lots'],
                                                                                  'use_existing_lots': n['use_existing_lots'],
                                                                                  'show_operations': n['show_operations'],
                                                                                  'show_reserved': n['show_reserved'],
                                                                                  'barcode': n['barcode'],
                                                                                  'company_id': n['company_id'][0]
                                                                                  })
                    print(new_stockpickingtype)
        return

    def action_down_ir_sequence(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model ir.sequence
        filtro = [[]]
        count_irsequence = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'ir.sequence', 'search_count', filtro)
        list_irsequence = models_cloud.execute_kw(lc_db, uid, lc_pass, 'ir.sequence', 'search_read', filtro, {'fields': ['id',
                                                                                                                         'name',
                                                                                                                         'code',
                                                                                                                         'implementation',
                                                                                                                         'active',
                                                                                                                         'prefix',
                                                                                                                         'suffix',
                                                                                                                         'number_next',
                                                                                                                         'number_increment',
                                                                                                                         'padding',
                                                                                                                         'company_id',
                                                                                                                         'use_date_range',
                                                                                                                         'number_next_actual'],
                                                                                                              'order': 'id'
                                                                                                              })
        for n in list_irsequence:
            print("---------------------------------------ir.sequence------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id'] != False):
                search_irsequence = self.env['ir.sequence'].search(
                    [('id', '=', n['id'])])
                if search_irsequence.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo y
                    # la secuencia de la nube es mayor que la secuencia local
                    if n['number_increment'] > search_irsequence.number_increment:
                        print("--------------actualizando en local----------")
                        update_irsequence = search_irsequence.write(
                            {
                                'name': n['name'],
                                'code': n['code'],
                                'implementation': n['implementation'],
                                'active': n['active'],
                                'prefix': n['prefix'],
                                'suffix': n['suffix'],
                                'number_next': n['number_next'],
                                'number_increment': n['number_increment'],
                                'padding': n['padding'],
                                'company_id': self.norma_false(n['company_id']),
                                'use_date_range': n['use_date_range'],
                                'number_next_actual': n['number_next_actual']
                            }
                        )
                        print(update_irsequence)
                    else:
                        print("------- actualizando en la nube ----------")
                        resp_irsequence = models_cloud.execute_kw(lc_db, uid, lc_pass, 'ir.sequence', 'write', [[n['id']], {
                            'number_next': search_irsequence.number_next,
                            'number_next_actual': search_irsequence.number_next_actual,
                        }])
                        print(" * Id de ir_sequence actualizado: ",
                              resp_irsequence)

                else:
                    # De lo contrario id no existe y hay q crear el registro
                    print("------------- Creando -------------------")
                    new_irsequence = self.env['ir.sequence'].create({'id': n['id'],
                                                                     'name': n['name'],
                                                                     'code': n['code'],
                                                                     'implementation': n['implementation'],
                                                                     'active': n['active'],
                                                                     'prefix': n['prefix'],
                                                                     'suffix': n['suffix'],
                                                                     'number_next': n['number_next'],
                                                                     'number_increment': n['number_increment'],
                                                                     'padding': n['padding'],
                                                                     # n['company_id'][0]
                                                                     'company_id': self.norma_false(n['company_id']),
                                                                     'use_date_range': n['use_date_range'],
                                                                     'number_next_actual': n['number_next_actual']
                                                                     })
                    print(new_irsequence)

        return

    def action_down_account_analytic(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model account.analytic.account
        filtro = [[]]
        count_account_analytic = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'account.analytic.account', 'search_count', filtro)
        list_account_analytic = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account', 'search_read', filtro, {'fields': ['id',
                                                                                                                                            'name',
                                                                                                                                            'code',
                                                                                                                                            'active',
                                                                                                                                            'group_id',
                                                                                                                                            'company_id',
                                                                                                                                            'partner_id',
                                                                                                                                            'message_main_attachment_id'],
                                                                                                                                 'order': 'id'}
                                                        )
        for n in list_account_analytic:
            print("---------------------------------------account.analytic.account------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            search_account_analytic = self.env['account.analytic.account'].search(
                [('code', '=', n['code'])])
            if search_account_analytic.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_account_analytic = search_account_analytic.write({'id': n['id'],
                                                                         'name': n['name'],
                                                                         'code': n['code'],
                                                                         'active': n['active'],
                                                                         'group_id': self.norma_false(n['group_id']),
                                                                         'company_id': self.norma_false(n['company_id']),
                                                                         'partner_id': self.norma_false(n['partner_id']),
                                                                         'message_main_attachment_id': None})
                print(update_account_analytic)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new__account_analytic = self.env['account.analytic.account'].create({
                    'name': n['name'],
                    'code': n['code'],
                    'active': n['active'],
                    'group_id': self.norma_false(n['group_id']),
                    'company_id': self.norma_false(n['company_id']),
                    'partner_id': self.norma_false(n['partner_id']),
                    'message_main_attachment_id': None}
                )
                print(new__account_analytic)
        return

    def action_down_project(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model project.project
        filtro = [[]]
        count_project = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'project.project', 'search_count', filtro)
        list_project = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.project', 'search_read', filtro, {'fields': ['id',
                                                                                                                          'name',
                                                                                                                          'description',
                                                                                                                          'active',
                                                                                                                          'sequence',
                                                                                                                          'partner_id',
                                                                                                                          'partner_email',
                                                                                                                          'partner_phone',
                                                                                                                          'company_id',
                                                                                                                          'analytic_account_id',
                                                                                                                          'label_tasks',
                                                                                                                          'color',
                                                                                                                          'user_id',
                                                                                                                          'alias_id',
                                                                                                                          'privacy_visibility',
                                                                                                                          'date_start',
                                                                                                                          'date',
                                                                                                                          'subtask_project_id',
                                                                                                                          'allow_subtasks',
                                                                                                                          'allow_recurring_tasks',
                                                                                                                          'rating_request_deadline',
                                                                                                                          'rating_active',
                                                                                                                          'rating_status',
                                                                                                                          'rating_status_period',
                                                                                                                          'access_token',
                                                                                                                          'message_main_attachment_id'],
                                                                                                               'order': 'id'}
                                               )
        listsearch_account_analytic_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account',
                                                                   'search_read',
                                                                   [()],
                                                                   {'fields': ['id', 'code'], 'order': 'id'})
        for n in list_project:
            print("---------------------------------------project.project------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar account_analytic_id de la nuube en local
            lc_code = self.search_en_listsearched(
                'id', n['analytic_account_id'][0], listsearch_account_analytic_nube, 'code')
            search_analytic_account_id_local = self.env['account.analytic.account'].search([
                                                                                           ('code', '=', lc_code)])
            # Buscar si existe: id
            search_project = self.env['project.project'].search(
                [('name', '=', n['name'])])
            if search_project.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_project = search_project.write({'id': n['id'],
                                                       'name': n['name'],
                                                       'alias_id': self.norma_false(n['alias_id']),
                                                       'privacy_visibility': n['privacy_visibility'],
                                                       'rating_status': n['rating_status'],
                                                       'rating_status_period': n['rating_status_period'],
                                                       'active': n['active'],
                                                       'description': n['description'],
                                                       'company_id': self.norma_false(n['company_id']),
                                                       'partner_id': self.norma_false(n['partner_id']),
                                                       'analytic_account_id': search_analytic_account_id_local.id,
                                                       'message_main_attachment_id': None})
                print(update_project)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new_project = self.env['project.project'].create({
                    'id': n['id'],
                    'name': n['name'],
                    'alias_id': self.norma_false(n['alias_id']),
                    'privacy_visibility': n['privacy_visibility'],
                    'rating_status': n['rating_status'],
                    'rating_status_period': n['rating_status_period'],
                    'active': n['active'],
                    'description': n['description'],
                    'company_id': self.norma_false(n['company_id']),
                    'partner_id': self.norma_false(n['partner_id']),
                    'analytic_account_id': search_analytic_account_id_local.id,
                    'message_main_attachment_id': None}
                )
                print(new_project)
        return

    def action_down_project_phase(self):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model project.task.phase
        filtro = [[]]
        count_project_phase = models_cloud.execute_kw(
            lc_db, uid, lc_pass, 'project.task.phase', 'search_count', filtro)
        list_project_phase = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.task.phase', 'search_read', filtro, {'fields': ['id',
                                                                                                                                   'name',
                                                                                                                                   'sequence',
                                                                                                                                   'project_id',
                                                                                                                                   'start_date',
                                                                                                                                   'end_date',
                                                                                                                                   'company_id',
                                                                                                                                   'user_id',
                                                                                                                                   'notes'],
                                                                                                                        'order': 'id'}
                                                     )
        listsearch_project_phase_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.project',
                                                                'search_read',
                                                                [()],
                                                                {'fields': ['id', 'name'], 'order': 'id'})
        for n in list_project_phase:
            print("---------------------------------------project.task.phase------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar project.task.phase de la nube en local
            if (n['project_id'] == False):
                # Solo buscar si la phase pertenece a algun proyecto!!! Si project_id es Falso entonces no hay asignado proyecto
                continue
            lc_name = self.search_en_listsearched(
                'id', n['project_id'][0], listsearch_project_phase_nube, 'name')
            search_project_id_local = self.env['project.project'].search(
                [('name', '=', lc_name)])
            # Buscar si existe: id
            search_project_phase = self.env['project.task.phase'].search(
                [('name', '=', n['name']), ('project_id', '=', search_project_id_local.id)])
            if search_project_phase.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_project_phase = search_project_phase.write({'id': n['id'],
                                                                   'name': n['name'],
                                                                   'sequence': n['sequence'],
                                                                   'project_id': search_project_id_local.id,
                                                                   'start_date': n['start_date'],
                                                                   'end_date': n['end_date'],
                                                                   'company_id': self.norma_false(n['company_id']),
                                                                   'user_id': None,
                                                                   'notes': n['notes']}
                                                                  )
                print(update_project_phase)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new_project_phase = self.env['project.task.phase'].create({
                    'id': n['id'],
                    'name': n['name'],
                    'sequence': n['sequence'],
                    'project_id': search_project_id_local.id,
                    'start_date': n['start_date'],
                    'end_date': n['end_date'],
                    'company_id': self.norma_false(n['company_id']),
                    'user_id': None,
                    'notes': n['notes']}
                )
                print(new_project_phase)

        return

    def action_up_stock_picking(self):
        # ver los registros del encabezado de las transferencias
        self.get_register_stock_picking()
        self.action_cierre()
        # Analizar cuales registros no has sido exportados a servidor en la nube
        #   Se necesita agregar campos al modelo: stock.picking
        #       export
        #       export_datetime
        #       export_user_id
        #       export_url
        #       export_checksum
        # ver los registros del detalle de las transferencias
        #     self.get_registers_stock_move()
        self.action_down_ir_sequence()
        
        return

    def action_down_masters_cloud(self):
        import time
        lt_time_ini = time.time()
        self.action_down_users()
        self.action_down_partners()
        self.action_down_stock_warehouse()
        self.action_down_stock_location()
        ####### ojo ################
        self.action_down_ir_sequence()
        ###################
        self.action_down_stock_picking_type()
        self.action_down_products()
        self.action_down_stock_quant()
        self.action_down_account_analytic()
        self.action_down_project()
        self.action_down_project_phase()
        lt_time_fin = time.time()
        ln_delta = lt_time_fin - lt_time_ini
        print(" * * * * * * * * * * * * * Delta: ")
        print(ln_delta)
        # To do!!!
        # tasks
        return

    ###################################################################################################################
    ################################################     STOCK MOVE    ################################################
    ###################################################################################################################
    def get_register_stock_move(self, ln_picking_id_local, ln_picking_id_cloud, partner_id_lh):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return

        # Lista de product_product en la nube
        list_products_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.product', 'search_read',
                                                      [[]], {'fields': ['id', 'default_code', 'product_tmpl_id']})
        # model: cloud o nube: stock.move; solo los no exportados; estos registros vienen referenciados por id desde el modelo: 'stock.picking'
        print("----------------------------------------------cloud: stock.move---------------------------------------------------")
        lc_filtro = [[['picking_id', '=', ln_picking_id_cloud]]]
        print("Buscando en cloud: picking.move resistros con id: ")
        print(lc_filtro)
        list_stock_move_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.move', 'search_read',
                                                        lc_filtro, {'fields': ['id',
                                                                               'name', 'location_id', 'picking_id', 'reference'], 'order': 'id'})
        if not list_stock_move_cloud:
            print(
                "------------------------------------------->>> Creando registros en 'stock.move' ")
            # 1. obtener los registros de local: stock.move
            list_stock_move_local = self.env['stock.move'].search(
                [('picking_id', '=', ln_picking_id_local)])
            # 2. asignar las cantidad de registros a una varaible para el ciclo for
            # 3. iterar o recorrer todos lo registros locales y crearlos en cloud
            for x_list in list_stock_move_local:
                # buscando id de product en la nube con local
                ln_product_id_on_local = self.norma_none_id(x_list.product_id)
                #####################################################################################################
                # Buscando id de phase en la nube: phase_id_on_azure: linea por linea: producto por producto
                # 0. Buscar el nombre del phase_id_local: phase_name_local
                phase_name_local = x_list.phase_id.name
                # a. Buscar project_id_local con (x_list.analytic_account_id)
                # search_project_id_on_local(self.norma_none_id(x_list.analytic_account_id))
                project_id_local = x_list.analytic_account_id.project_ids.id
                project_name_local = x_list.analytic_account_id.project_ids.name
                # b. Buscar project_id_cloud con (project_id_local)
                if not x_list.analytic_account_id.project_ids.name:
                    project_id_cloud = None
                else:
                    project_id_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.project', 'search_read',
                                                               [[['name', '=', x_list.analytic_account_id.project_ids.name]]])[0]['id']  # search_project_id_on_cloud(project_id_local)
                    # c. Buscar list_phase_cloud con (project_id_cloud)
                if project_id_cloud == None:
                    list_phases_cloud = []
                    phase_id_on_azure = None
                else:
                    list_phases_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.task.phase', 'search_read',
                                                                [[['project_id', '=', project_id_cloud]]])  # lista_de_phases_del_proyecto_en_la_nube
                    # d. Buscar phase_id_on_cloud con (list_phases_cloud, phase_name_local)
                    phase_id_on_azure = self.search_phase_id_on_cloud(
                        phase_name_local, list_phases_cloud)
                phase_id_on_local = self.norma_none_id(x_list.phase_id)
                # Lotes = Cuentas Analiticas
                list_analytic_account_cloud2 = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account', 'search_read',
                                                                       [[]], {'fields': ['id', 'name', 'code', 'partner_id']})
                #####################################################################################################
                # product_id_lh = search_product_id_on_cloud(item_id, list_products_cloud)
                lc_default_code_local = self.env['product.product'].search_read(
                    [['id', '=', ln_product_id_on_local]])
                for xlist in list_products_cloud:
                    if xlist['default_code'] == lc_default_code_local[0]['default_code']:
                        ln_product_id_on_cloud = xlist['id']
                        ln_product_id_on_cloud_tmpl = xlist['product_tmpl_id']
                        break
                    else:
                        ln_product_id_on_cloud = False
                        ln_product_id_on_cloud_tmpl = False
                        continue
                product_id_lh = ln_product_id_on_cloud
                if not ln_product_id_on_cloud_tmpl:
                    product_uom_cl = False
                else:
                    lc_filtro = [[['id', '=', ln_product_id_on_cloud_tmpl[0]]]]
                    product_template = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.template', 'search_read', lc_filtro,
                                                               {'fields': ['id', 'uom_id']})
                    product_uom_cl = product_template[0]['uom_id'][0]
                ##########
                try:
                    resp_l = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.move', 'create',
                                                     [{
                                                         'name': x_list.name,
                                                         'sequence': x_list.sequence,
                                                         'priority': x_list.priority,
                                                         'date': x_list.date,
                                                         'date_deadline': x_list.date_deadline,
                                                         'product_id': product_id_lh,
                                                         'description_picking': x_list.description_picking,
                                                         'product_uom_qty': x_list.product_uom_qty,
                                                         'product_uom': product_uom_cl,
                                                         'location_id': self.norma_none_id(x_list.location_id),
                                                         'location_dest_id': self.norma_none_id(x_list.location_dest_id),
                                                         'partner_id': partner_id_lh,
                                                         'picking_id': ln_picking_id_cloud,
                                                         'note': x_list.note,
                                                         'state': x_list.state,
                                                         'price_unit': x_list.price_unit,
                                                         'origin': x_list.origin,
                                                         'procure_method': x_list.procure_method,
                                                         'scrapped': x_list.scrapped,
                                                         'group_id': self.norma_none_id(x_list.group_id),
                                                         'rule_id': self.norma_none_id(x_list.rule_id),
                                                         'propagate_cancel': x_list.propagate_cancel,
                                                         'delay_alert_date': x_list.delay_alert_date,
                                                         'picking_type_id': self.norma_none_id(x_list.picking_type_id),
                                                         'inventory_id': self.norma_none_id(x_list.inventory_id),
                                                         'origin_returned_move_id': self.norma_none_id(x_list.origin_returned_move_id),
                                                         'restrict_partner_id': self.norma_none_id(x_list.restrict_partner_id),
                                                         'warehouse_id': self.norma_none_id(x_list.warehouse_id),
                                                         'additional': x_list.additional,
                                                         'reference': x_list.reference,
                                                         'package_level_id': self.norma_none_id(x_list.package_level_id),
                                                         'next_serial': x_list.next_serial,
                                                         'orderpoint_id': self.norma_none_id(x_list.next_serial_count),
                                                         'to_refund': x_list.to_refund,
                                                         'analytic_account_id': self.norma_none_id(self.search_analytic_account_id_on_cloud(x_list.analytic_account_id, list_analytic_account_cloud2)),
                                                         'category_id': self.norma_none_id(x_list.category_id),
                                                         'phase_id': self.norma_none_id(phase_id_on_azure),
                                                         'next_serial_count': x_list.next_serial_count
                                                     }])
                    # 'product_qty': x_list.product_qty,
                    # self.norma_none_id(x_list.product_uom),
                    print("***Registro creado en stock.move")
                    print(resp_l)
                except Exception as err:
                    print(
                        ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                    raise
                    # return
        else:
            print("--->>> Actualizando registros en 'stock.move' ")
        return

    def search_product_id_on_cloud(self, ln_product_id_on_local, list_products_cloud):
        # lc_ref_local = self.env['res.partner'].search_read([['id','=',ln_partner_id_on_local.id]])
        lc_default_code_local = self.env['product.product'].search_read(
            [['id', '=', ln_product_id_on_local.id]])
        for xlist in list_products_cloud:
            if xlist['default_code'] == lc_default_code_local[0]['default_code']:
                ln_product_id_on_cloud = xlist['id']
                break
            else:
                ln_product_id_on_cloud = False
                continue
        return ln_product_id_on_cloud

    def search_phase_id_on_cloud(self, lc_phase_name_local, list_phases_cloud):
        for y_list in list_phases_cloud:
            if y_list['name'] == lc_phase_name_local:
                v_return = y_list['id']
                break
            else:
                v_return = False
                continue
        return v_return

    ###################################################################################################################
    ################################################   STOCK PICKING   ################################################
    ###################################################################################################################
    def get_register_stock_picking(self):
        # crear o reemplazar la vista temp a de stock.picking: esta es una imagen justo antes de exportar para control y
        # verificacion de datos
        string_view_query = """create or replace view stock_picking_vistatemp_a as select * from public.stock_picking sp
            where sp.export != true or sp.export isnull """
        self.env.cr.execute(string_view_query)
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url = 'http://' + self.server_url.server_url
        lc_db = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            # User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ", uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy(
                '{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                                    'res.partner', 'check_access_rights',
                                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(err)
            print(
                ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model: cloud o nube: stock.picking; solo los no exportados
        lc_filtro = [[]]
        list_stock_picking_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'search_read',
                                                           lc_filtro, {'fields': ['id',
                                                                                  'name', 'location_id', 'message_main_attachment_id', 'state'], 'order': 'id'})
        list_stock_location_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_read',
                                                            lc_filtro, {'fields': ['id',
                                                                                   'name', 'parent_path'], 'order': 'id'})
        list_res_partner_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.partner', 'search_read',
                                                         [[]], {'fields': ['id', 'name', 'ref']})
        list_res_users_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.users', 'search_read',
                                                       [[]], {'fields': ['id', 'name', 'login']})
        # Lotes = Cuentas Analiticas
        list_analytic_account_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account', 'search_read',
                                                              [[]], {'fields': ['id', 'name', 'code', 'partner_id']})
        # empezar a trabajar con la busqueda en el modelo: 'stock.picking' solo los registros que no han sido marcados exportados
        # O sea: en un ciclo for iterar y subir (up-load) al modelo en la url del servidor en la nube
        regs_stock_picking_not_exported = self.env['stock.picking'].search(
            ['|', ('export', '=', False), ('export_datetime', '=', False), ('is_locked', '=', True), ('state', '=', 'done')])
        print("--------: Registros no exportados: --------")
        print(regs_stock_picking_not_exported)
        list_stock_picking_ids = []
        for registro_local in regs_stock_picking_not_exported:
            print("#####################################################################################################################")
            print("---------------------------------------cloud: stock.picking------------------------------------------------------------")
            print("#####################################################################################################################")
            lc_mens = registro_local['name']
            print(lc_mens)
            # Buscar 'name' local en la nube
            if (registro_local['name'] == False):
                # Solo buscar si name es difernte de False
                continue
            # Buscar si existe: name y location
            # Validar: location_id local en la nube: esto se hace por si id de la nube no coincide con el local
            location_id_local = registro_local['location_id']
            lc_location_parent_path = self.search_en_listsearched(
                'id', location_id_local.id, list_stock_location_cloud, 'parent_path')
            try:
                search_location_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_read', [
                                                                [['parent_path', '=', lc_location_parent_path]]])
            except Exception as err:
                print(
                    ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                raise
                return
            #
            if search_location_cloud == False:
                print("ERROR:-----------------: No se encontro el id del parent_path en stock.location de la nube: " + lc_location_parent_path)
                continue
            else:
                location_id_cloud = search_location_cloud[0]['id']
            print("Buscando la transferencia id en la nube: ")
            ll_registro_cloud = self.search_en_listsearched2(
                'name', 'location_id', registro_local['name'], location_id_cloud, list_stock_picking_cloud)
            if ll_registro_cloud == False:
                print(
                    "---- NO SE ENCONTRO EL REGISTRO DE LA TRANSFERENCIA EN LA NUBE ----: " + lc_mens)
            else:
                print("SI SE ENCONTRO:")
                print(ll_registro_cloud)
            partner_id_l = self.search_partner_id_on_cloud(
                registro_local.partner_id, list_res_partner_cloud)
            # Si no existe el registro en la nube
            if not ll_registro_cloud:
                # si no existe: entonces crearlo
                print("+-*-+*/*/*/*/*********** Crear stock.picking  ******>>>>>")
                try:
                    resp = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'create',
                                                   [{
                                                       'name': registro_local.name,
                                                       'origin': (registro_local.origin),
                                                       'note': (registro_local.note),
                                                       'backorder_id': self.norma_none(registro_local.backorder_id),
                                                       'move_type': registro_local.move_type,
                                                       'state': registro_local.state,
                                                       'group_id': self.norma_none(registro_local.group_id),
                                                       'priority': '0',
                                                       'scheduled_date': registro_local.scheduled_date.isoformat(sep=' ', timespec='seconds'),
                                                       'date_deadline': self.norma_none(registro_local.date_deadline),
                                                       'has_deadline_issue': registro_local.has_deadline_issue,
                                                       'date': registro_local.date,
                                                       'date_done': registro_local.date_done,
                                                       'location_id': self.norma_none_id(registro_local.location_id),
                                                       'location_dest_id': self.norma_none_id(registro_local.location_dest_id),
                                                       'picking_type_id': self.norma_none_id(registro_local.picking_type_id),
                                                       'partner_id': partner_id_l,
                                                       'company_id': self.norma_none_id(registro_local.company_id),
                                                       'user_id': self.search_user_id_on_cloud(registro_local.user_id, list_res_users_cloud),
                                                       'owner_id': self.norma_none_id(registro_local.owner_id),
                                                       'printed': registro_local.printed,
                                                       'is_locked': registro_local.is_locked,
                                                       'immediate_transfer': registro_local.immediate_transfer,
                                                       'message_main_attachment_id': self.insert_ir_attachment(registro_local.message_main_attachment_id, models_cloud, lc_db, uid, lc_pass, 0),
                                                       'full_analytic_account_id': self.norma_none(self.search_analytic_account_id_on_cloud(registro_local.full_analytic_account_id, list_analytic_account_cloud))
                                                   }]
                                                   )
                    print(resp)
                    resp_picking_id = resp
                except Exception as err:
                    print(err)
                    print(
                        ">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                    raise
                    return
                # agregar los id subidos a la nube a una lista de id de picking
                list_stock_picking_ids.append(registro_local)
                print(registro_local)
                # ","","","","","","create_uid","create_date","write_uid","write_date",""
                # crear los registros en el modelo: 'stock.move'
                picking_id_cloud = resp_picking_id
                picking_id_local = registro_local.id
                # stock.move
                self.get_register_stock_move(
                    picking_id_local, picking_id_cloud, partner_id_l)
                ####################################################
                # actualizar los campos 'export' en la tabla: 'stock.picking' que lograron ser exportados!
            # Si existe el registro en la nube
            else:
                # Solo se actualizan los registro no 'done'
                if ll_registro_cloud['state'] != 'done':
                    # buscar el registro en la nube si existe: entonces se debe actualizar si y solo si ha cambiado! *(1)'export_checksum'
                    print("+-*-+------->>>  Actualizar stock.picking------>>>>>>>")

                    try:
                        if not ll_registro_cloud['message_main_attachment_id']:
                            message_id = 0
                        else:
                            message_id = ll_registro_cloud['message_main_attachment_id'][0]
                        resp = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'write',
                                                       [[ll_registro_cloud['id']], {
                                                           'name': registro_local.name,
                                                           'origin': (registro_local.origin),
                                                           'note': (registro_local.note),
                                                           'backorder_id': self.norma_none(registro_local.backorder_id),
                                                           'move_type': registro_local.move_type,
                                                           'state': registro_local.state,
                                                           'group_id': self.norma_none(registro_local.group_id),
                                                           'priority': '0',
                                                           'scheduled_date': registro_local.scheduled_date.isoformat(sep=' ', timespec='seconds'),
                                                           'date_deadline': self.norma_none(registro_local.date_deadline),
                                                           'has_deadline_issue': registro_local.has_deadline_issue,
                                                           'date': registro_local.date,
                                                           'date_done': registro_local.date_done,
                                                           'location_id': self.norma_none_id(registro_local.location_id),
                                                           'location_dest_id': self.norma_none_id(registro_local.location_dest_id),
                                                           'picking_type_id': self.norma_none_id(registro_local.picking_type_id),
                                                           'partner_id': partner_id_l,
                                                           'company_id': self.norma_none_id(registro_local.company_id),
                                                           'user_id': self.search_user_id_on_cloud(registro_local.user_id, list_res_users_cloud),
                                                           'owner_id': self.norma_none_id(registro_local.owner_id),
                                                           'printed': registro_local.printed,
                                                           'is_locked': registro_local.is_locked,
                                                           'immediate_transfer': registro_local.immediate_transfer,
                                                           'message_main_attachment_id': self.insert_ir_attachment(registro_local.message_main_attachment_id, models_cloud, lc_db, uid, lc_pass, message_id),
                                                           'full_analytic_account_id': 408,  # registro_local.full_analytic_account_id
                                                       }]
                                                       )
                        print(resp)
                        resp_picking_id = ll_registro_cloud['id']
                    except Exception as err:
                        print(
                            ">>>>>>>>>>>>>-------1604--- Inesperado/Unexpected {err=}, {type(err)=}")
                        raise
                        # return
                else:
                    print(
                        'Registro no se actualizo por que su estatus es: ' + 'done/hecho')
                    # Marcar el registro local como: exportado = True
                    # search_project_id_local = self.env['project.project'].search([('name','=',lc_name)])
                    # Buscar si existe: id
                    # search_project_phase = self.env['project.task.phase'].search([('name','=',n['name']), ('project_id','=',search_project_id_local.id)])
                    # if search_project_phase.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print("------------actualizando registro ya exportado----------")
                    update_registro_local = registro_local.write({
                        'export': True,
                        'export_datetime': fields.Datetime.now(),
                        'export_url': socket.gethostname(),
                        'export_user_id': registro_local.user_id
                    }
                    )
                    print(update_registro_local)

                    ##########
        print("*******************************************************************lista de ids de picking exportandas: ")
        print(list_stock_picking_ids)
        return

    def insert_ir_attachment(self, message_attachment, models_cloud_l, lc_db_l, uid_l, lc_pass_l, id_adjunto_si_existe):
        print("--------   cloud ir.attachment     --------")
        # buscar si existe llave unica: 'name' en la conexion 'models_cloud'
        print("---> Buscando adjunto: ")
        print(message_attachment['name'])
        message_cloud = models_cloud_l.execute_kw(lc_db_l, uid_l, lc_pass_l, 'ir.attachment', 'search_read',
                                                  [[['name', '=', message_attachment['name']]]])
        if not message_attachment['name']:
            print("No se pudo buscar el adjunto; porque 'name' del adjunto es False.")
            return False
        # Si existe el mensaje: actualizar
        if id_adjunto_si_existe != 0:
            # if ((not message_cloud) == False): --- se elimino porque la busqueda no funciona!!!
            # entonces actualizar
            print(">--------------- Actualizando el adjunto")
            resp_cloud = models_cloud_l.execute_kw(lc_db_l, uid_l, lc_pass_l, 'ir.attachment', 'write',
                                                   [[id_adjunto_si_existe], {'name': message_attachment.name,
                                                                             'description': message_attachment.description,
                                                                             'res_model': message_attachment.res_model,
                                                                             'res_field': message_attachment.res_field,
                                                                             'res_id': message_attachment.res_field,
                                                                             'company_id': self.norma_none_id(message_attachment.company_id),
                                                                             'type': message_attachment.type,
                                                                             'url': message_attachment.url,
                                                                             'public': message_attachment.public,
                                                                             'access_token': message_attachment.access_token,
                                                                             'datas': message_attachment.datas,
                                                                             'db_datas': message_attachment.db_datas,
                                                                             'store_fname': message_attachment.store_fname,
                                                                             'file_size': message_attachment.file_size,
                                                                             'checksum': message_attachment.checksum,
                                                                             'mimetype': message_attachment.mimetype,
                                                                             'index_content': message_attachment.index_content,
                                                                             'original_id': self.norma_none(message_attachment.original_id)
                                                                             }])
            print(resp_cloud)
            ln_id_ir_attachment = resp_cloud

        else:
            # si no existe entonces: crear
            print(">--------------- Creando el adjunto")
            resp_cloud = models_cloud_l.execute_kw(lc_db_l, uid_l, lc_pass_l, 'ir.attachment', 'create',
                                                   [{'name': message_attachment.name,
                                                     'description': message_attachment.description,
                                                     'res_model': message_attachment.res_model,
                                                     'res_field': message_attachment.res_field,
                                                     'res_id': message_attachment.res_field,
                                                     'company_id': self.norma_none_id(message_attachment.company_id),
                                                       'type': message_attachment.type,
                                                       'url': message_attachment.url,
                                                       'public': message_attachment.public,
                                                       'access_token': message_attachment.access_token,
                                                       'datas': message_attachment.datas,
                                                       'db_datas': message_attachment.db_datas,
                                                       'store_fname': message_attachment.store_fname,
                                                       'file_size': message_attachment.file_size,
                                                       'checksum': message_attachment.checksum,
                                                       'mimetype': message_attachment.mimetype,
                                                       'index_content': message_attachment.index_content,
                                                       'original_id': self.norma_none(message_attachment.original_id)
                                                     }])
            print(resp_cloud)
            ln_id_ir_attachment = resp_cloud
        return ln_id_ir_attachment

    def search_user_id_on_cloud(self, ln_user_id_on_local, list_res_users_cloud):
        lc_login_local = self.env['res.users'].search_read(
            [['id', '=', ln_user_id_on_local.id]])
        for xlist in list_res_users_cloud:
            if xlist['login'] == lc_login_local[0]['login']:
                ln_user_id_on_cloud = xlist['id']
                break
            else:
                ln_user_id_on_cloud = False
                continue
        return ln_user_id_on_cloud

    def search_partner_id_on_cloud(self, ln_partner_id_on_local, list_res_partner_cloud):
        lc_ref_local = self.env['res.partner'].search_read(
            [['id', '=', ln_partner_id_on_local.id]])
        for xlist in list_res_partner_cloud:
            if xlist['ref'] == lc_ref_local[0]['ref']:
                ln_partner_id_on_cloud = xlist['id']
                break
            else:
                ln_partner_id_on_cloud = False
                continue
        return ln_partner_id_on_cloud

    def search_analytic_account_id_on_cloud(self, ln_analytic_accoint_id_on_local, list_analytic_account_cloud):
        lc_code_local = self.env['account.analytic.account'].search_read(
            [['id', '=', ln_analytic_accoint_id_on_local.id]])
        if len(lc_code_local) == 0:
            # return False
            return None
        for xlist in list_analytic_account_cloud:
            if xlist['code'] == lc_code_local[0]['code']:
                ln_analytic_accoount_id_on_cloud = xlist['id']
                break
            else:
                ln_analytic_accoount_id_on_cloud = False
                continue
        return ln_analytic_accoount_id_on_cloud

    def norma_none(self, lvalor):
        clase_tipo = type(lvalor)
        if not lvalor:
            if type(lvalor) == str:
                return ''
            else:
                return False
        else:
            return lvalor

    def norma_none_id(self, lvalor):
        clase_tipo = type(lvalor)
        if not lvalor:
            return False
        else:
            if type(lvalor) == int:
                return lvalor
            else:
                return lvalor.id

    def norma_false(self, lvalor):
        if not lvalor:
            return None
        else:
            return lvalor[0]

    def norma_false_string(self, lvalor):
        if not lvalor:
            return ''
        else:
            return lvalor

    def norma_false_date(self, lvalor):
        if not lvalor:
            return datetime.datetime(1900, 1, 1, 0, 0, 0)
        else:
            return lvalor

    def search_en_listsearched(self, field_search, id_nube_model, listlist, field_return):
        for x_list in listlist:
            if x_list[field_search] == id_nube_model:
                ret = x_list[field_return]
                break
            else:
                ret = ''
                continue
        return ret

    def search_en_listsearched2(self, field_search1, field_search2, id_nube_model1, id_nube_model2, listlist):
        for x_list in listlist:
            if x_list[field_search1] == id_nube_model1 and x_list[field_search2][0] == id_nube_model2:
                ret = x_list
                break
            else:
                ret = False
                continue
        return ret

    def action_cierre(self):
        from datetime import datetime
        # A. HACER CONSULTA DEL CIERRE
        fecha_cierre = self.fecha_cierre_sync
        archivo = self._cierre_transfers(fecha_cierre)
        # B. ENVIAR EL CORREO
        # B.1. CONSULTAR SI HAY REGISTROS DE TRANSFERENCIAS SIN MARCAR PARA LA FECHA_CIERRE
        etiqueta = self._get_regs_sin_marcar(fecha_cierre)
        if etiqueta == "SIN REGISTROS":
            print(etiqueta)
        elif etiqueta == "CON REGISTROS ALGUNOS MARCADOS" or etiqueta == "CON REGISTROS NINGUNO MARCADOS":
            self._enviar_correo_con_adjunto(archivo, fecha_cierre)
            self._marcar_cierre(fecha_cierre)
        elif etiqueta == "CON REGISTROS TODOS MARCADOS":
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! - Todo Marcado - !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! para esta fecha", fecha_cierre.date())
            mensaje = "Todos los Registros de Trasfs. estan Marcados.  Desea volver a enviar correo del Cierre?"
            if self.accion_cierre == "Si":
                self._enviar_correo_con_adjunto(archivo, fecha_cierre)
                self._marcar_cierre(fecha_cierre)
        else:
            print("CASO NO DEFINIDO..............................................................................................")
        # 3. marcar los registros de transferencias en el campo: 'close' y la fecha de cierre
        
        return False
    
    def _get_regs_sin_marcar(self, fecha_cierre=None):
        #tools.drop_view_if_exists(self.env.cr, self._table)
        from datetime import date
        from io import BytesIO
        import base64
        import xlsxwriter
        # 1. crear el informe de cierre de transferencia de inventario xls
            # 1.a. crear la consulta sql de las transferencias del dia corriente
        #fecha_filtro = date.today()
        ##########################################################################################################################3
        from datetime import datetime
        import pytz
        if fecha_cierre==False or fecha_cierre==None:
            fecha_cierre = datetime.now()
                
        user = self.env.user  # Obtener el usuario actual
        filtro_utc_dt = fecha_cierre  # Fecha y hora actual en UTC
        # Convertir la fecha y hora actual de UTC a la zona horaria del usuario
        if user.tz:
            local_tz = pytz.timezone(user.tz)
            filtro_local_dt = filtro_utc_dt.astimezone(local_tz)
        else:
            filtro_local_dt = filtro_utc_dt
        # Ahora current_local_dt contiene la fecha y hora actuales en la zona horaria del usuario
        #########################################################################################################################3
        fecha_filtro = filtro_local_dt.date()
        # Ejecutar la primera consulta
        query1 = ("""
            SELECT name, date_done, close, close_datetime
            FROM public.stock_picking
            where date_done::timestamp::date = %s
        """)
        self.env.cr.execute(query1, (fecha_filtro,))
        # Asignar los resultados a la primera variable
        all_records = self.env.cr.fetchall()

        # Ejecutar la segunda consulta
        query2 = ("""
            SELECT name, date_done, close, close_datetime
            FROM public.stock_picking
            where "close" = true and date_done::timestamp::date = %s
        """)

        # Asignar los resultados a la segunda variable
        self.env.cr.execute(query2, (fecha_filtro,))
        marked_records = self.env.cr.fetchall()
        # Registros si marcas
        regs_sin_marca = len(all_records) - len(marked_records)
        if len(all_records) == 0:
            etiqueta = "SIN REGISTROS"
        else:
            if len(all_records) == len(marked_records):
                etiqueta = "CON REGISTROS TODOS MARCADOS"
            else:
                if regs_sin_marca == 0:
                    etiqueta = "CON REGISTROS NINGUNO MARCADOS"
                else:
                    etiqueta = "CON REGISTROS ALGUNOS MARCADOS"
        return etiqueta
    
    def _marcar_cierre(self, fecha_cierre):
        # Buscar registros donde date_done es igual a fecha_cierre
        stock_picking_obj = self.env['stock.picking']
        ##########################################################################################################################3
        from datetime import datetime
        import pytz
        user = self.env.user  # Obtener el usuario actual
        current_utc_dt = fecha_cierre  # Fecha y hora actual en UTC
        # Convertir la fecha y hora actual de UTC a la zona horaria del usuario
        if user.tz:
            local_tz = pytz.timezone(user.tz)
            current_local_dt = current_utc_dt.astimezone(local_tz)
        else:
            current_local_dt = current_utc_dt
        # Ahora current_local_dt contiene la fecha y hora actuales en la zona horaria del usuario
        #########################################################################################################################3
        stock_picking_records = stock_picking_obj.search([])  # Buscamos todos los registros
        regs_marcados = 0
        for record in stock_picking_records:
            date_done = record.date_done.date() if record.date_done else False  # Convertimos datetime a date
            if date_done == current_local_dt.date():
                # Aquí va tu lógica si la fecha de finalización es igual a la fecha actual
                # Actualizar los campos close y close_datetime para esos registros
                regs_marcados = record.write({
                    'close': True,
                    'close_datetime': fields.Datetime.now(),
                })
                regs_marcados = regs_marcados + 1
        print("se marcaron: ", regs_marcados)
        return regs_marcados
    
    def _cierre_transfers(self, fecha_cierre):
        from datetime import date
        from io import BytesIO
        import base64
        import xlsxwriter
        # 1. crear el informe de cierre de transferencia de inventario xls
            # 1.a. crear la consulta sql de las transferencias del dia corriente
        #fecha_filtro = date.today()
        ##########################################################################################################################3
        from datetime import datetime
        import pytz
        user = self.env.user  # Obtener el usuario actual
        filtro_utc_dt = fecha_cierre  # Fecha y hora actual en UTC
        # Convertir la fecha y hora actual de UTC a la zona horaria del usuario
        if user.tz:
            local_tz = pytz.timezone(user.tz)
            filtro_local_dt = filtro_utc_dt.astimezone(local_tz)
        else:
            filtro_local_dt = filtro_utc_dt
        # Ahora current_local_dt contiene la fecha y hora actuales en la zona horaria del usuario
        #########################################################################################################################3
        fecha_filtro = filtro_local_dt.date()
        self.env['project.vsqlcss'].init(fecha_filtro)
        # Consulta los datos
        records = self.env['project.vsqlcss'].search([])
            # 1.b. convertir la consulta sql a archivo en formato xls
        # Crear un objeto en memoria para guardar el archivo Excel
        output = BytesIO()
        # Usar la biblioteca para crear el archivo Excel
        # Aquí un ejemplo simplificado usando xlsxwriter
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        # Cabeceras de columnas
        headers = ['Nombre Producto', 'Fecha', 'Paquete Inventario', 'Documento Inventario',
                   'linea', 'articulo', 'bodega', 'cantidad', 'ajuste_configurable', 'tipo',
                   'subtipo', 'subsubtipo', 'centro_costo', 'fase', 'cuenta_contable',
                   'orden_cambio', 'notes', 'company_id', 'proyecto', 'bodega_origen', 'bodega_destino',
                   'referencia', 'tipo_recolecion', 'codigo_contratista']  # Añade todos los campos relevantes aquí
        # Escribe las cabeceras en el archivo Excel
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)
        # Escribe los datos en el archivo Excel
        row_num = 1
        for record in records:
            row = [
                record.name,
                record.fecha,
                record.paquete_inventario,
                record.documento_inventario,
                record.linea,
                record.articulo,
                record.bodega,
                record.cantidad,
                record.ajuste_configurable,
                record.tipo,
                record.subtipo,
                record.subsubtipo,
                record.centro_costo,
                record.fase,
                record.cuenta_contable,
                record.orden_cambio,
                record.notes,
                record.company_id.name,
                record.proyecto,
                record.bodega_origen,
                record.bodega_destino,
                record.referencia,
                record.tipo_recoleccion,
                record.codigo_contratista
            ]
            for col_num, cell_value in enumerate(row):
                worksheet.write(row_num, col_num, cell_value)
            row_num += 1
        
        workbook.close()
        output.seek(0)
        # 2, devolver el archivo del informe
        return output

    def _enviar_correo_con_adjunto(self, archivo_xlsx, fecha_cierre):
        ##########################################################################################################################3
        from datetime import datetime
        import pytz
        if fecha_cierre==False or fecha_cierre==None:
            fecha_cierre = datetime.now()
                
        user = self.env.user  # Obtener el usuario actual
        #filtro_utc_dt = fecha_cierre  # Fecha y hora actual en UTC
        # Convertir la fecha y hora actual de UTC a la zona horaria del usuario
        if user.tz:
            local_tz = pytz.timezone(user.tz)
            filtro_local_dt = fecha_cierre.astimezone(local_tz)
        else:
            filtro_local_dt = fecha_cierre
        # Ahora current_local_dt contiene la fecha y hora actuales en la zona horaria del usuario
        #########################################################################################################################3
        fecha_correo = filtro_local_dt.date()

        # Contenido del correo
        body_html = """
            <h3>Hola,</h3>
            <p>Este es un mensaje automático de cierre de las transferencias con fecha {fecha_correo} desde Odoo .</p>
        """.format(fecha_correo=fecha_correo)
        fecha_larga = fecha_correo.strftime('%A %d de %B del %Y')
        body_html_pro = f"""<!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial;
                    margin: 0;
                    padding: 0;
                    background-color: #f0f0f0;
                    justify-content: center;
                    align-items: center;
                }}
                .container {{
                    width: 80%;
                    margin: 0 auto;
                    background-color: #fff;
                    padding: 20px;
                    border-radius: 5px;
                    margin-top: 10px;
                    box-shadow: 1px 1px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    padding: 10px;
                    background-color: #007BFF;
                    color: white;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Notificación Automática</h2>
                </div>
                <div class="sub-header">
                    <h1>{fecha_larga}</h1>
                </div>
                <div class="content">
                    <p>Hola,</p>
                    <p>Este es un mensaje automático de cierre de las transferencias con fecha corriente desde Odoo.</p>
                    <p>Por favor, no responda a este correo electrónico. Si tiene alguna pregunta, póngase en contacto con nuestro equipo de soporte.</p>
                    <p>Gracias,</p>
                    <p>El equipo de INURBAN-ALCONSOFT</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Crear el archivo adjunto
        attachment_data = {
            'name': self.env.user.company_id.name + '_transferencias_' + fecha_correo.strftime("%Y-%m-%d") + '.xlsx',
            'res_model': 'self',
            'res_id': self.id,
            'type': 'binary',
            'datas': base64.b64encode(archivo_xlsx.getvalue())
        }
        attachment = self.env['ir.attachment'].create(attachment_data)
        # Obtenga el registro del modelo 'server_url'
        emails_registros = self.env['res.users'].browse(self.server_url.email_destino_cierre.ids)

        # Extraiga los valores del campo 'login' de esos registros
        login_values = [record.login for record in emails_registros]

        # Crear el correo
        for emailto in login_values:
            mail_values = {
                'subject': self.env.user.company_id.name + ' Transferencias ' + fecha_correo.strftime("%Y-%m-%d"),
                'body_html': body_html_pro,
                'email_to': emailto, #'soporte@inurbansa.com',
                'attachment_ids': [(6, 0, [attachment.id])]
            }
            print(mail_values)
            mail = self.env['mail.mail'].create(mail_values)
            resp = mail.send()
            print("Respuesta de corrreo: ", resp)

        return True

    estado_de_registros_marcados_cerrado = fields.Char("Estado de Registros Cerrados: ", default=_get_regs_sin_marcar)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    export = fields.Boolean('Is Exported', default=False)
    export_datetime = fields.Datetime(string='Date exported')
    export_user_id = fields.Many2one('res.users', string='User ID:')
    export_url = fields.Char(string='Exported to url:')
    close = fields.Boolean('Closed', default=False)
    close_datetime = fields.Datetime(string='Date closed')

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        # Define los valores predeterminados para los campos al duplicar
        default = dict(default or {})
        default.update({
            'export': False,  # Suponiendo que 'export' es un campo booleano
            'export_datetime': False,  # Reinicia el campo datetime
            'export_user_id': False,  # Reinicia el campo de usuario (Many2one)
            'export_url': False,  # Suponiendo que 'export_url' es un campo Char o Text
            'close': False,  # Suponiendo que 'close' es un campo booleano
            'close_datetime': False,  # Reinicia el campo datetime
            'full_analytic_account_id': False,
        })

        # Llama al método copy original de la clase padre
        res = super(StockPicking, self).copy(default=default)
        # Inicializa el campo analytic_account_id en todos los registros relacionados de stock.move
        for move in res.move_ids_without_package:
            move.analytic_account_id = False

        self.ver_detalles()

        return res
#En este código, al duplicar el registro, los campos especificados se inicializan a un valor predeterminado
#  (en la mayoría de los casos, simplemente se reinician). Asumí algunos tipos de datos para los campos en base a sus nombres,
#  así que ajusta según sea necesario.
# PENDIENTE: campo suma de verificacion: esto es para saber si la fila o el registro del encabezaso de
#   la transferencia ha cambiado y por lo tanot se debe actualizar


class SyncDownPartner(models.Model):
    _inherit = 'res.partner'

    type = fields.Selection(
        [('contact', 'Contact'),
         ('contractor', 'Contractor'),
         ('invoice', 'Invoice Address'),
         ('delivery', 'Delivery Address'),
         ('other', 'Other Address'),
         ("private", "Private Address"),
         ], string='Address Type',
        default='contractor',
        help="Invoice & Delivery addresses are used in sales orders. Private addresses are only visible by authorized users.")
