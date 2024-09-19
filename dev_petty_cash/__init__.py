# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from . import models
from . import report
#from . import controllers


def pre_init_check(cr):
    from odoo.service import common
    from odoo.exceptions import UserError
    from odoo import _
    version_info = common.exp_version()
    server_serie = version_info.get('server_serie')
    if server_serie != '16.0':
        raise UserError(_("This Application is only supported in 16.0 version of odoo !"))
    return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
