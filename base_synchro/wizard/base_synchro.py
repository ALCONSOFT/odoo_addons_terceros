# See LICENSE file for full copyright and licensing details.

from ast import For
import datetime
import logging
from ssl import AlertDescription
import threading
import time
from xmlrpc.client import ServerProxy
from odoo import api, fields, models
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

    server_url = fields.Many2one(
        "base.synchro.server", "Server URL", required=True
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
                value = pool_src.get(object.model_id.model).read([id], fields)[0]
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
                            idnew = pool_dest.env[object.model_id.model].create(value)
                            new_id = idnew.id
                        else:
                            idnew = pool_dest.env[object.model_id.model].create(value)
                            new_id = idnew.id
                    elif object.model_id.model == "stock.move.line":
                        a = value.pop('product_qty')
                        b = value.pop('product_uom_qty')
                        idnew = pool_dest.env[object.model_id.model].create(value)
                        idnew.write({
                            'product_uom_qty': b
                        })
                        new_id = idnew.id
                    else:
                        idnew = pool_dest.env[object.model_id.model].create(value)
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
                query_str = 'SELECT "%s".id FROM ' % pool_dest.env[obj_model]._table + from_clause + where_str
                order_by = pool_dest.env[obj_model]._generate_order_by(None, query_str)
                query_str = query_str + order_by
                pool_dest.env[obj_model]._cr.execute(query_str, where_clause_params)
                res1 = self._cr.fetchall()
                res = [ls[0] for ls in res1]
                result = res[0]
            if obj_model == "stock.picking.type":
                names = pool_src.get(obj_model).name_get([res_id])[0][1]
                name = names.split(':')[0].strip()
                res = pool_dest.env[obj_model]._name_search(name, [], "like")
                from_clause, where_clause, where_clause_params = res.get_sql()
                where_str = where_clause and (" WHERE %s" % where_clause) or ''
                query_str = 'SELECT "%s".id FROM ' % pool_dest.env[obj_model]._table + from_clause + where_str
                order_by = pool_dest.env[obj_model]._generate_order_by(None, query_str)
                query_str = query_str + order_by
                pool_dest.env[obj_model]._cr.execute(query_str, where_clause_params)
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
                    res = pool_dest.env[obj_model]._name_search(name, [], "like")
                    res = [res]
                elif obj_model == "res.country":
                    names = pool_src.get(obj_model).name_get([res_id])[0][1]
                    res = pool_dest.env[obj_model]._name_search(names, [], "=")
                    res = [[res[0]]]
                else:
                    names = pool_src.get(obj_model).name_get([res_id])[0][1]
                    res = pool_dest.env[obj_model].name_search(names, [], "like")
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
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model res_users on cloud
        filtro =  [[['active','=',True]]]
        count_users = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.users', 'search_count', filtro)
        list_users = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.users', 'search_read', filtro, {'fields': ['name', 'login', 'password', 'company_id'] })
        for n in list_users:
            print(n)
            # Buscar si el id o llave priamria existe en res.users
            search_user = self.env['res.users'].search([('login', '=', n['login'])])
            # Guardar registro list_users[n] en res.users local
            if search_user.active == False:
                new_user = self.env['res.users'].create({'name': n['name'], 'login': n['login'], 'password':n['password'], 'company_id':n['company_id'][0]})
        #except Exception:
        #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return

    def action_down_partners(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model res_partener
        filtro =  [[['active','=',True],]]
        count_partners = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.partner', 'search_count', filtro)
        list_partners = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.partner', 'search_read', filtro, {'fields': ['name',
            'company_id',
            'display_name',
            'ref',
            'active',
            'type',
            'is_company',
            'company_name',
            'supplier_rank'] })
        for n in list_partners:
            print(n)
            lc_mens = n['name']
            # Buscar si el id o llave primaria existe en res.partner.  si tiene ref hacer la busqueda.
            if  (n['ref']!=False):
                search_partner = self.env['res.partner'].search([('ref', '=', n['ref'])])
                # Guardar registro list_partner[n] en res.partner local
                if search_partner.active == False:
                    new_partner = self.env['res.partner'].create({'name': n['name'],
                        'display_name': n['display_name'],
                        'ref':n['ref'],
                        'company_id':n['company_id'][0],
                        'active':n['active'],
                        'type':n['type'],
                        'is_company':n['is_company'],
                        'company_name':n['company_name'],
                        'supplier_rank':n['supplier_rank']})
            else:
                print("Partner name no tiene codigo de referencia: " + lc_mens)
            #except Exception:
            #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return

    def action_down_products(self):
        #self.action_down_uoms() ; da muchos problemas con los tipos de unidades de medidas
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model product_template
        filtro =  [[['active','=',True],]]
        count_producttemplate = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.template', 'search_count', filtro)
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
            'order':'id' } )
        for n in list_producttemplate:
            print(n)
            reg_pt = self.action_down_product_template(n)
            ln_idpt = reg_pt.id
            #ln_idpp = self.action_down_product_quant(n, ln_idpt)
        return

    def action_down_stock_quant(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model stock.quant
        filtro =  [[]]
        count_stockquant = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.quant', 'search_count', filtro)
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
            'order':'id'
        })
        listsearch_product_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'product.product',
            'search_read',
            [()],
            {'fields': ['id', 'default_code'], 'order':'id'})
        listsearch_location_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location',
            'search_read',
            [()],
            {'fields': ['id', 'name', 'parent_path'], 'order':'id'})
        for n in list_stockquant:
            print("---------------------------------------stock quant------------------------------------------------------------")
            print(n)
            lc_mens = n['product_id'][1]
            # product
            product_id_nube_quant = n['product_id'][0]
            lc_defaul_code = self.search_en_listsearched('id', product_id_nube_quant, listsearch_product_nube, 'default_code')
            search_product_local = self.env['product.product'].search([('default_code','=',lc_defaul_code)])
            # location
            location_id_nube_quant = n['location_id'][0]
            lc_location_parent_path = self.search_en_listsearched('id', location_id_nube_quant, listsearch_location_nube, 'parent_path')
            search_location_local = self.env['stock.location'].search([('parent_path','=',lc_location_parent_path)])
            # lot
            lot_id_nube_quant = self.norma_false(n['lot_id'])
            # buscar en tabla quant local
            if search_product_local.id==False or search_location_local.id==False:
                continue
            else:
                lc_filtro = [('product_id','=',search_product_local.id),
                    ('location_id','=',search_location_local.id),
                    ('lot_id','=',lot_id_nube_quant)]
            # Buscar si existe: id
            search_stockquant = self.env['stock.quant'].search(lc_filtro)
            if search_stockquant.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("----------------Actualizando-----------------")
                update_stockquant = search_stockquant.write(
                    {
                    'product_id':search_product_local.id,
                    'company_id':self.norma_false(n['company_id']),
                    'location_id':search_location_local.id,
                    'lot_id':lot_id_nube_quant,
                    'package_id':n['package_id'],
                    'owner_id':n['owner_id'],
                    'quantity':n['quantity'],
                    'reserved_quantity':n['reserved_quantity'],
                    'in_date':n['in_date']
                    }
                )
            else:
                # El id no existe asi que se creara
                print("----------------Creando------------------------")
                new_stockquant = self.env['stock.quant'].create({
                    'product_id':search_product_local.id,
                    'company_id':self.norma_false(n['company_id']),
                    'location_id':search_location_local.id,
                    'lot_id':lot_id_nube_quant,
                    'package_id':n['package_id'],
                    'owner_id':n['owner_id'],
                    'quantity':n['quantity'],
                    'reserved_quantity':n['reserved_quantity'],
                    'in_date':n['in_date']
                    }
                )
                print(new_stockquant)
        return

    def action_down_product_template(self, n):
        lc_mens = n['name']
        # Buscar si el id o llave primaria existe en res.partner. Si tiene default_code hacer la busqueda
        if  (n['default_code']!=False):
            search_producttemplate = self.env['product.template'].search([('default_code', '=', n['default_code'])])
            # Decidi Normalizar las unidades de medida a Unit id=1 de todos los productos
            # Guardar registro list_producttemplate[n] en product_template local
            if search_producttemplate.active == False:
                new_producttemplate = self.env['product.template'].create({'name': n['name'],
                    'description': n['description'],
                    'type':n['type'],
                    'categ_id':n['categ_id'][0],
                    'sale_ok':n['sale_ok'],
                    'purchase_ok':n['purchase_ok'],
                    'uom_id':1,
                    'active':n['active'],
                    'default_code':n['default_code'],
                    'uom_po_id':1,
                    'tracking':n['tracking'] })
        else:
            print("Product Template name no tiene codigo de referencia: " + lc_mens)
        # Guardar registro en product_product
        #except Exception:
        #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        return new_producttemplate
    
    def action_down_stock_warehouse(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model sotck.warehouse
        filtro =  [[['active','=',True],]]
        count_stockwarehouse = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.warehouse', 'search_count', filtro)
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
            'order':'id' } )
        for n in list_stockwarehouse:
            print(n)
            lc_mens = n['name']
            # Buscar si el id o llave primaria existe en stock.warehouse.  si tiene "code" hacer la busqueda.
            # CONDICION ESPECIAL: asumiremos que WH=0001.  Por lo tanto si el code de la bodega local = "WH";
            #   solo cambiaremos los campos: NAME y CODE
            if (n['code']!=False):
                codigo_bodega_nube = n['code']
                codigo_bodega_local = self.env['stock.warehouse'].search([('code','=','WH')])
                if codigo_bodega_local.id != False:
                    # Si el codigo_bodega_local no es False: entonces existe WH
                    # y cambiaremos name y code:  Se ha asumido que los demas paramentros son iguales en ambas bases de datos
                    search_stockwarehouse = self.env['stock.warehouse'].search([('code', '=', 'WH')])
                    # Actualizar registro list_stockwarehouse[n] en stock.warehouse local
                    new_stockwarehouse = search_stockwarehouse.write({'name': n['name'],
                        'code': n['code'] } )
                else:
                    # Si no entonces: no existe WH y puede ser que code="0001"
                    if codigo_bodega_nube == '0001':
                        # actualizar todos los parametros de la bodega: 001
                        search_stockwarehouse = self.env['stock.warehouse'].search([('code', '=', n['code'])])
                        new_stockwarehouse = search_stockwarehouse.write({'name': n['name'],
                            'partner_id':n['partner_id'][0],
                            'view_location_id':n['view_location_id'][0],
                            'lot_stock_id':n['lot_stock_id'][0],
                            'reception_steps':n['reception_steps'],
                            'active':n['active'],
                            'delivery_steps':n['delivery_steps'],
                            'wh_input_stock_loc_id':n['wh_input_stock_loc_id'][0],
                            'wh_qc_stock_loc_id':n['wh_qc_stock_loc_id'][0],
                            'wh_output_stock_loc_id':n['wh_output_stock_loc_id'][0],
                            'wh_pack_stock_loc_id':n['wh_pack_stock_loc_id'][0],
                            'mto_pull_id':n['mto_pull_id'][0],
                            'pick_type_id':n['pick_type_id'][0],
                            'pack_type_id':n['pack_type_id'][0],
                            'out_type_id':n['out_type_id'][0],
                            'in_type_id':n['in_type_id'][0],
                            'int_type_id':n['int_type_id'][0],
                            'crossdock_route_id':n['crossdock_route_id'][0],
                            'reception_route_id':n['reception_route_id'][0],
                            'delivery_route_id':n['delivery_route_id'][0],
                            'sequence':n['sequence']} )
                    else:
                        # La bodega no existe y hay que crearla; pero solo se permite una bodega o warehouse
                        # Pendiente de programacion: Alconsoft 3-nov-2022
                        print("-*--")
            else:
                print("Warehouse name no tiene codigo de referencia: " + lc_mens)
            #except Exception:
            #    print("Hubo un error al tratar de conectar al servidor base de datos Destino Odoo14: ")
        print("+++++++++++++++++++++++++++++++ FIN DE WWAREHOUSE ++++++++++++++++++++++++++++++++++++++++++++++++++")
        return

    def action_down_stock_location(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model sotck.location
        filtro =  [[]]
        count_stocklocation = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_count', filtro)
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
            'order':'id' }
        )
        for n in list_stocklocation:
            print("---------------------------------------stock location------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id']!=False):
                search_stocklocation = self.env['stock.location'].search([('id','=',n['id'])])
                if search_stocklocation.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print("----------------Actualizando-----------------")
                    update_stocklocation = search_stocklocation.write(
                        {
                            'name':n['name'],
                            'complete_name': n['complete_name'],
                            'active':n['active'],
                            'usage':n['usage'],
                            'location_id':self.norma_false(n['location_id']),
                            'comment':n['comment'],
                            'posx':n['posx'],
                            'posy':n['posy'],
                            'posz':n['posz'],
                            'parent_path':n['parent_path'],
                            'scrap_location':n['scrap_location'],
                            'return_location':n['return_location'],
                            'removal_strategy_id':self.norma_false(n['removal_strategy_id']),
                            'barcode':n['barcode'],
                            'valuation_in_account_id':self.norma_false(n['valuation_in_account_id']),
                            'valuation_out_account_id':self.norma_false(n['valuation_out_account_id'])
                        }
                    )
                else:
                    # El id no existe asi que se creara
                    print("----------------Creando-----------------'id':n['id'],")
                    new_stocklocation = self.env['stock.location'].create({
                            'name':n['name'],
                            'complete_name': n['complete_name'],
                            'active':n['active'],
                            'usage':n['usage'],
                            'location_id':self.norma_false(n['location_id']),
                            'company_id':self.norma_false(n['company_id']),
                            'comment':n['comment'],
                            'posx':n['posx'],
                            'posy':n['posy'],
                            'posz':n['posz'],
                            'parent_path':n['parent_path'],
                            'scrap_location':n['scrap_location'],
                            'return_location':n['return_location'],
                            'removal_strategy_id':self.norma_false(n['removal_strategy_id']),
                            'barcode':n['barcode'],
                            'valuation_in_account_id':self.norma_false(n['valuation_in_account_id']),
                            'valuation_out_account_id':self.norma_false(n['valuation_out_account_id'])
                        }
                    )
                    print(new_stocklocation)
        return

    def action_down_stock_picking_type(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model sotck.picking.type
        filtro =  [[]]
        count_stockpickingtype = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking.type', 'search_count', filtro)
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
            'order':'id' } )
        for n in list_stockpickingtype:
            print("---------------------------------------stock picking type------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id']!=False):
                search_stockpickingtype = self.env['stock.picking.type'].search([('id','=',n['id'])])
                if search_stockpickingtype.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print("--------------actualizando---- 'return_picking_type_id':n['return_picking_type_id'][0],------")
                    update_stockpickingtype = search_stockpickingtype.write(
                        {
                            'name':n['name'],
                            'color':n['color'],
                            'sequence':n['sequence'],
                            'sequence_id':n['sequence_id'][0],
                            'sequence_code':n['sequence_code'],
                            'default_location_src_id':n['default_location_src_id'][0],
                            'default_location_dest_id':n['default_location_dest_id'][0],
                            'code':n['code'],
                            'show_entire_packs':n['show_entire_packs'],
                            'warehouse_id':n['warehouse_id'][0],
                            'active':n['active'],
                            'use_create_lots':n['use_create_lots'],
                            'use_existing_lots':n['use_existing_lots'],
                            'show_operations':n['show_operations'],
                            'show_reserved':n['show_reserved'],
                            'barcode':n['barcode'],
                            'company_id':n['company_id'][0]
                        }
                    )
                else:
                    # De lo contrario id no existe y hay q crear el registro
                    print("------------- Creando -------------------")
                    new_stockpickingtype = self.env['stock.picking.type'].create({'id':n['id'],
                            'name':n['name'],
                            'color':n['color'],
                            'sequence':n['sequence'],
                            'sequence_id':n['sequence_id'][0],
                            'sequence_code':n['sequence_code'],
                            'default_location_src_id':n['default_location_src_id'][0],
                            'default_location_dest_id':n['default_location_dest_id'][0],
                            'code':n['code'],
                            'show_entire_packs':n['show_entire_packs'],
                            'warehouse_id':n['warehouse_id'][0],
                            'active':n['active'],
                            'use_create_lots':n['use_create_lots'],
                            'use_existing_lots':n['use_existing_lots'],
                            'show_operations':n['show_operations'],
                            'show_reserved':n['show_reserved'],
                            'barcode':n['barcode'],
                            'company_id':n['company_id'][0]
                    })
                    print(new_stockpickingtype)
        return

    def action_down_ir_sequence(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model ir.sequence
        filtro =  [[]]
        count_irsequence = models_cloud.execute_kw(lc_db, uid, lc_pass, 'ir.sequence', 'search_count', filtro)
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
            'use_date_range'],
            'order':'id'
        })
        for n in list_irsequence:
            print("---------------------------------------ir.sequence------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            if (n['id']!=False):
                search_irsequence = self.env['ir.sequence'].search([('id','=',n['id'])])
                if search_irsequence.id != False:
                    # Si el id no es False: entonces existe! y hay q actualizarlo
                    print("--------------actualizando----------")
                    update_irsequence = search_irsequence.write(
                        {
                            'name':n['name'],
                            'code':n['code'],
                            'implementation':n['implementation'],
                            'active':n['active'],
                            'prefix':n['prefix'],
                            'suffix':n['suffix'],
                            'number_next':n['number_next'],
                            'number_increment':n['number_increment'],
                            'padding':n['padding'],
                            'company_id':self.norma_false(n['company_id']),
                            'use_date_range':n['use_date_range']
                        }
                    )
                    print(update_irsequence)
                else:
                    # De lo contrario id no existe y hay q crear el registro
                    print("------------- Creando -------------------")
                    new_irsequence = self.env['ir.sequence'].create({'id':n['id'],
                            'name':n['name'],
                            'code':n['code'],
                            'implementation':n['implementation'],
                            'active':n['active'],
                            'prefix':n['prefix'],
                            'suffix':n['suffix'],
                            'number_next':n['number_next'],
                            'number_increment':n['number_increment'],
                            'padding':n['padding'],
                            'company_id':n['company_id'][0],
                            'use_date_range':n['use_date_range']
                    })
                    print(new_irsequence)

        return
    
    def action_down_account_analytic(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model account.analytic.account
        filtro =  [[]]
        count_account_analytic = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account', 'search_count', filtro)
        list_account_analytic = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account', 'search_read', filtro, {'fields': ['id',
            'name',
            'code',
            'active',
            'group_id',
            'company_id',
            'partner_id',
            'message_main_attachment_id'],
            'order':'id'}
        )
        for n in list_account_analytic:
            print("---------------------------------------account.analytic.account------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar si existe: id
            search_account_analytic = self.env['account.analytic.account'].search([('code','=',n['code'])])
            if search_account_analytic.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_account_analytic = search_account_analytic.write({'id':n['id'],
                    'name':n['name'],
                    'code':n['code'],
                    'active':n['active'],
                    'group_id':self.norma_false(n['group_id']),
                    'company_id':self.norma_false(n['company_id']),
                    'partner_id':self.norma_false(n['partner_id']),
                    'message_main_attachment_id':None})
                print(update_account_analytic)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new__account_analytic = self.env['account.analytic.account'].create({
                    'name':n['name'],
                    'code':n['code'],
                    'active':n['active'],
                    'group_id':self.norma_false(n['group_id']),
                    'company_id':self.norma_false(n['company_id']),
                    'partner_id':self.norma_false(n['partner_id']),
                    'message_main_attachment_id':None}
                )
                print(new__account_analytic)
        return
    
    def action_down_project(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model project.project
        filtro =  [[]]
        count_project = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.project', 'search_count', filtro)
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
            'order':'id'}
        )
        listsearch_account_analytic_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'account.analytic.account',
            'search_read',
            [()],
            {'fields': ['id', 'code'], 'order':'id'})
        for n in list_project:
            print("---------------------------------------project.project------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar account_analytic_id de la nuube en local
            lc_code = self.search_en_listsearched('id', n['analytic_account_id'][0], listsearch_account_analytic_nube, 'code')
            search_analytic_account_id_local = self.env['account.analytic.account'].search([('code','=',lc_code)])
            # Buscar si existe: id
            search_project = self.env['project.project'].search([('name','=',n['name'])])
            if search_project.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_project = search_project.write({'id':n['id'],
                    'name':n['name'],
                    'alias_id':self.norma_false(n['alias_id']),
                    'privacy_visibility':n['privacy_visibility'],
                    'rating_status':n['rating_status'],
                    'rating_status_period':n['rating_status_period'],
                    'active':n['active'],
                    'description':n['description'],
                    'company_id':self.norma_false(n['company_id']),
                    'partner_id':self.norma_false(n['partner_id']),
                    'analytic_account_id':search_analytic_account_id_local.id,
                    'message_main_attachment_id':None})
                print(update_project)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new_project = self.env['project.project'].create({
                    'id':n['id'],
                    'name':n['name'],
                    'alias_id':self.norma_false(n['alias_id']),
                    'privacy_visibility':n['privacy_visibility'],
                    'rating_status':n['rating_status'],
                    'rating_status_period':n['rating_status_period'],
                    'active':n['active'],
                    'description':n['description'],
                    'company_id':self.norma_false(n['company_id']),
                    'partner_id':self.norma_false(n['partner_id']),
                    'analytic_account_id':search_analytic_account_id_local.id,
                    'message_main_attachment_id':None}
                )
                print(new_project)
        return

    def action_down_project_phase(self):
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        #try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_url)
        print("common version: ", common.version())
        #User Identifier
        uid = common.authenticate(lc_db, lc_user, lc_pass, {})
        print("uid: ",uid)
        # Calliing methods
        models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_url))
        models_cloud.execute_kw(lc_db, uid, lc_pass,
                'res.partner', 'check_access_rights',
                ['read'], {'raise_exception': False})
        # model project.task.phase
        filtro =  [[]]
        count_project_phase = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.task.phase', 'search_count', filtro)
        list_project_phase = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.task.phase', 'search_read', filtro, {'fields': ['id',
            'name',
            'sequence',
            'project_id',
            'start_date',
            'end_date',
            'company_id',
            'user_id',
            'notes'],
            'order':'id'}
        )
        listsearch_project_phase_nube = models_cloud.execute_kw(lc_db, uid, lc_pass, 'project.project',
            'search_read',
            [()],
            {'fields': ['id', 'name'], 'order':'id'})
        for n in list_project_phase:
            print("---------------------------------------project.task.phase------------------------------------------------------------")
            print(n)
            lc_mens = n['name']
            # Buscar project.task.phase de la nube en local
            if (n['project_id']==False):
                # Solo buscar si la phase pertenece a algun proyecto!!! Si project_id es Falso entonces no hay asignado proyecto
                continue
            lc_name = self.search_en_listsearched('id', n['project_id'][0], listsearch_project_phase_nube, 'name')
            search_project_id_local = self.env['project.project'].search([('name','=',lc_name)])
            # Buscar si existe: id
            search_project_phase = self.env['project.task.phase'].search([('name','=',n['name']), ('project_id','=',search_project_id_local.id)])
            if search_project_phase.id != False:
                # Si el id no es False: entonces existe! y hay q actualizarlo
                print("--------------actualizando----------")
                update_project_phase = search_project_phase.write({'id':n['id'],
                    'name':n['name'],
                    'sequence':n['sequence'],
                    'project_id':search_project_id_local.id,
                    'start_date':n['start_date'],
                    'end_date':n['end_date'],
                    'company_id':self.norma_false(n['company_id']),
                    'user_id':None,
                    'notes':n['notes']}
                )
                print(update_project_phase)
            else:
                # Hay q crear el registro
                print("--------------Creando----------")
                new_project_phase = self.env['project.task.phase'].create({
                    'id':n['id'],
                    'name':n['name'],
                    'sequence':n['sequence'],
                    'project_id':search_project_id_local.id,
                    'start_date':n['start_date'],
                    'end_date':n['end_date'],
                    'company_id':self.norma_false(n['company_id']),
                    'user_id':None,
                    'notes':n['notes']}
                )
                print(new_project_phase)

        return
    
    def action_up_stock_picking(self):
        # ver los registros del encabezado de las transferencias
        self.get_register_stock_picking()
        # Analizar cuales registros no has sido exportados a servidor en la nube
        #   Se necesita agregar campos al modelo: stock.picking
        #       export
        #       export_datetime
        #       export_user_id
        #       export_url
        #       export_checksum
        # ver los registros del detalle de las transferencias
        #     self.get_registers_stock_move()
        return
    
    ###################################################################################################################
    ################################################     STOCK MOVE    ################################################
    ###################################################################################################################
    def get_register_stock_move(self, ln_picking_id_local, ln_picking_id_cloud):
        # crear la conexion con el servidor en la url de la nube
        ln_id = self.id
        lc_name = self.server_url.name
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            #User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ",uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                    'res.partner', 'check_access_rights',
                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(f">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model: cloud o nube: stock.move; solo los no exportados; estos registros vienen referenciados por id desde el modelo: 'stock.picking'
        print("----------------------------------------------cloud: stock.move---------------------------------------------------")
        lc_filtro = [[['picking_id','=', ln_picking_id_cloud]]]
        print("Buscando en cloud: picking.move resistros con id: ")
        print(lc_filtro)
        list_stock_move_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.move', 'search_read',
            lc_filtro, {'fields': ['id',
            'name', 'location_id', 'picking_id','reference'], 'order':'id'})
        if not list_stock_move_cloud:
            print("--->>> Creando registros en 'picking.move' ")
            # 1. obtener los registros de local: stock.move
            list_stock_move_local = self.env['stock.move'].search([('picking_id','=',ln_picking_id_local)])
            # 2. asignar las cantidad de registros a una varaible para el ciclo for
            # 3. iterar o recorrer todos lo registros locales y crearlos en cloud
            for x_list in list_stock_move_local:
                resp_l = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.move', 'create',
                    [{
                        'name': list_stock_move_local[0]['name'],

                    }])

            """id                     
sequence               
priority               
create_date            
date                   
date_deadline          
company_id             
product_id             
description_picking    
product_qty            
product_uom_qty        
product_uom            
location_id            
location_dest_id       
partner_id             
picking_id             
note                   
state                  
price_unit             
origin                 
procure_method         
scrapped               
group_id               
rule_id                
propagate_cancel       
delay_alert_date       
picking_type_id        
inventory_id           
origin_returned_move_id
restrict_partner_id    
warehouse_id           
additional             
reference              
package_level_id       
next_serial            
next_serial_count      
orderpoint_id          
create_uid             
write_uid              
write_date             
to_refund              
analytic_account_id    
category_id            
phase_id               
old_edition             """
        else:
            print("--->>> Actualizando registros en 'picking.move' ")
        
        return


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
        lc_url  = 'http://' + self.server_url.server_url
        lc_db   = self.server_url.server_db
        lc_port = self.server_url.server_port
        lc_user = self.server_url.login
        lc_pass = self.server_url.password
        lc_pathurl = lc_url + ':' + str(lc_port)
        try:
            common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % lc_pathurl, allow_none=False)
            print("common version: ", common.version())
            #User Identifier
            uid = common.authenticate(lc_db, lc_user, lc_pass, {})
            print("uid: ",uid)
            # Calliing methods
            models_cloud = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(lc_pathurl))
            models_cloud.execute_kw(lc_db, uid, lc_pass,
                    'res.partner', 'check_access_rights',
                    ['read'], {'raise_exception': False})
        except Exception as err:
            print(f">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
            raise
            return
        # model: cloud o nube: stock.picking; solo los no exportados
        lc_filtro = [[]]
        list_stock_picking_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'search_read',
            lc_filtro, {'fields': ['id',
            'name', 'location_id', 'message_main_attachment_id'], 'order':'id'})
        list_stock_location_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_read',
            lc_filtro, {'fields': ['id',
            'name', 'parent_path'], 'order':'id'})
        list_res_partner_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.partner', 'search_read',
            [[]], {'fields':['id','name','ref']})
        list_res_users_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'res.users', 'search_read',
            [[]], {'fields':['id','name','login']})
        # empezar a trabajar con la busqueda en el modelo: 'stock.picking' solo los registros que no han sido marcados exportados
        # O sea: en un ciclo for iterar y subir (up-load) al modelo en la url del servidor en la nube
        regs_stock_picking_not_exported = self.env['stock.picking'].search([('export','=',False),('is_locked','=',True),('state','=','done')])
        list_stock_picking_ids = []
        for registro_local in regs_stock_picking_not_exported:
            print("#####################################################################################################################")
            print("---------------------------------------cloud: stock.picking------------------------------------------------------------")
            print("#####################################################################################################################")
            lc_mens = registro_local['name']
            print(lc_mens)
            # Buscar 'name' local en la nube
            if (registro_local['name']==False):
                # Solo buscar si name es difernte de False
                continue
            # Buscar si existe: name y location
            # Validar: location_id local en la nube: esto se hace por si id de la nube no coincide con el local
            location_id_local = registro_local['location_id']
            lc_location_parent_path = self.search_en_listsearched('id', location_id_local.id, list_stock_location_cloud, 'parent_path')
            try:
                search_location_cloud = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.location', 'search_read', [[['parent_path','=', lc_location_parent_path]]])
            except Exception as err:
                print(f">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                raise
                return
            # 
            if search_location_cloud == False:
                print("ERROR:-----------------: No se encontro el id del parent_path en stock.location de la nube: " + lc_location_parent_path)
                continue 
            else:
                location_id_cloud = search_location_cloud[0]['id']
            print("Buscando la transferencia id en la nube: ")
            ll_registro_cloud = self.search_en_listsearched2('name', 'location_id',registro_local['name'], location_id_cloud, list_stock_picking_cloud)
            if ll_registro_cloud == False:
                print("---- NO SE ENCONTRO EL REGISTRO DE LA TRANSFERENCIA EN LA NUBE ----: " + lc_mens)
            else:
                print("SI SE ENCONTRO:")
                print(ll_registro_cloud)

            if ll_registro_cloud != False:
                # buscar el registro en la nube si existe: entonces se debe actualizar si y solo si ha cambiado! *(1)'export_checksum'
                print("+-*-+------->>>  Actualizar stock.picking------>>>>>>>")
                try:
                    if not ll_registro_cloud['message_main_attachment_id']:
                        message_id = 0
                    else:
                        message_id = ll_registro_cloud['message_main_attachment_id'][0]
                    resp = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'write',
                        [ [ll_registro_cloud['id']], {
                        'name':registro_local.name,
                        'origin':(registro_local.origin),
                        'note':(registro_local.note),
                        'backorder_id':self.norma_none(registro_local.backorder_id),
                        'move_type':registro_local.move_type,
                        'state':registro_local.state,
                        'group_id':self.norma_none(registro_local.group_id),
                        'priority':'0',
                        'scheduled_date':registro_local.scheduled_date.isoformat(sep=' ',timespec='seconds'),
                        'date_deadline':self.norma_none(registro_local.date_deadline),
                        'has_deadline_issue':registro_local.has_deadline_issue,
                        'date':registro_local.date,
                        'date_done':registro_local.date_done,
                        'location_id':self.norma_none_id(registro_local.location_id),
                        'location_dest_id':self.norma_none_id(registro_local.location_dest_id),
                        'picking_type_id':self.norma_none_id(registro_local.picking_type_id),
                        'partner_id':self.search_partner_id_on_cloud(registro_local.partner_id, list_res_partner_cloud),
                        'company_id':self.norma_none_id(registro_local.company_id),
                        'user_id':self.search_user_id_on_cloud(registro_local.user_id, list_res_users_cloud),
                        'owner_id':self.norma_none_id(registro_local.owner_id),
                        'printed':registro_local.printed,
                        'is_locked':registro_local.is_locked,
                        'immediate_transfer':registro_local.immediate_transfer,
                        'message_main_attachment_id':self.insert_ir_attachment(registro_local.message_main_attachment_id, models_cloud, lc_db, uid, lc_pass, message_id),
                        'full_analytic_account_id':408,#registro_local.full_analytic_account_id
                        }]
                    )
                    print(resp)
                    resp_picking_id = ll_registro_cloud['id']
                except Exception as err:
                    print(">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                    raise
                    return

            # si no existe: entonces crearlo
            else:
                print("+-*-+*/*/*/*/*********** Crear stock.picking  ******>>>>>")
                try:
                    resp = models_cloud.execute_kw(lc_db, uid, lc_pass, 'stock.picking', 'create',
                        [{
                        'name':registro_local.name,
                        'origin':(registro_local.origin),
                        'note':(registro_local.note),
                        'backorder_id':self.norma_none(registro_local.backorder_id),
                        'move_type':registro_local.move_type,
                        'state':registro_local.state,
                        'group_id':self.norma_none(registro_local.group_id),
                        'priority':'0',
                        'scheduled_date':registro_local.scheduled_date.isoformat(sep=' ',timespec='seconds'),
                        'date_deadline':self.norma_none(registro_local.date_deadline),
                        'has_deadline_issue':registro_local.has_deadline_issue,
                        'date':registro_local.date,
                        'date_done':registro_local.date_done,
                        'location_id':self.norma_none_id(registro_local.location_id),
                        'location_dest_id':self.norma_none_id(registro_local.location_dest_id),
                        'picking_type_id':self.norma_none_id(registro_local.picking_type_id),
                        'partner_id':self.search_partner_id_on_cloud(registro_local.partner_id, list_res_partner_cloud),
                        'company_id':self.norma_none_id(registro_local.company_id),
                        'user_id':self.search_user_id_on_cloud(registro_local.user_id, list_res_users_cloud),
                        'owner_id':self.norma_none_id(registro_local.owner_id),
                        'printed':registro_local.printed,
                        'is_locked':registro_local.is_locked,
                        'immediate_transfer':registro_local.immediate_transfer,
                        'message_main_attachment_id':self.insert_ir_attachment(registro_local.message_main_attachment_id, models_cloud, lc_db, uid, lc_pass, 0),
                        'full_analytic_account_id':408,#registro_local.full_analytic_account_id
                        }]
                    )
                    print(resp)
                    resp_picking_id = resp
                except Exception as err:
                    print(">>>>>>>>>>>>>---------- Inesperado/Unexpected {err=}, {type(err)=}")
                    raise
                    return
            # agregar los id subidos a la nube a una lista de id de picking
            list_stock_picking_ids.append(registro_local)
            print(registro_local)
            #","","","","","","create_uid","create_date","write_uid","write_date",""
            # crear los registros en el modelo: 'stock.move'
            picking_id_cloud = resp_picking_id
            picking_id_local = registro_local.id
            #################################################### stock.move
            self.get_register_stock_move(picking_id_local, picking_id_cloud)
            ####################################################
            # actilizar los campos 'export' en la tabla: 'stock.picking' que lograron ser exportados!
        print("*******************************************************************lista de ids de picking exportandas: ")
        print(list_stock_picking_ids)
        return 

    def insert_ir_attachment(self, message_attachment, models_cloud_l, lc_db_l, uid_l, lc_pass_l, id_adjunto_si_existe):
        print("--------   cloud ir.attachment     --------")
        # buscar si existe llave unica: 'name' en la conexion 'models_cloud'
        print("---> Buscando adjunto: ")
        print(message_attachment['name'])
        message_cloud = models_cloud_l.execute_kw(lc_db_l, uid_l, lc_pass_l, 'ir.attachment', 'search_read',
            [[['name','=',message_attachment['name'] ] ]] )
        if not message_attachment['name']:
            print("No se pudo buscar el adjunto; porque 'name' del adjunto es False.")
            return False
        # Si existe el mensaje: actualizar
        if id_adjunto_si_existe != 0:
        #if ((not message_cloud) == False): --- se elimino porque la busqueda no funciona!!!
            # entonces actualizar
            print(">--------------- Actualizando el adjunto")
            resp_cloud = models_cloud_l.execute_kw(lc_db_l, uid_l, lc_pass_l, 'ir.attachment', 'write',
                [[id_adjunto_si_existe],{'name': message_attachment.name,
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
        lc_login_local = self.env['res.users'].search_read([['id','=',ln_user_id_on_local.id]])
        for xlist in list_res_users_cloud:
            if xlist['login'] == lc_login_local[0]['login']:
                ln_user_id_on_cloud = xlist['id']
                break
            else:
                ln_user_id_on_cloud = False
                continue
        return ln_user_id_on_cloud


    def search_partner_id_on_cloud(self, ln_partner_id_on_local, list_res_partner_cloud):
        lc_ref_local = self.env['res.partner'].search_read([['id','=',ln_partner_id_on_local.id]])
        for xlist in list_res_partner_cloud:
            if xlist['ref'] == lc_ref_local[0]['ref']:
                ln_partner_id_on_cloud = xlist['id']
                break
            else:
                ln_partner_id_on_cloud = False
                continue
        return ln_partner_id_on_cloud
    
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
            return datetime.datetime(1900,1,1,0,0,0)
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

class StockPicking(models.Model):
    _inherit='stock.picking'

    export = fields.Boolean('Is Exported', default=False)
    export_datetime = fields.Datetime(string='Date exported')
    export_user_id = fields.Many2one('res.users',string='User ID:')
    export_url = fields.Char(string='Exported to url:')
    # PENDIENTE: campo suma de verificacion: esto es para saber si la fila o el registro del encabezaso de
    #   la transferencia ha cambiado y por lo tanot se debe actualizar

class SyncDownPartner(models.Model):
    _inherit='res.partner'

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