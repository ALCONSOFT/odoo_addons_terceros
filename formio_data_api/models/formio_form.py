# Copyright Nova Code (https://www.novacode.nl)
# See LICENSE file for full licensing details.

import logging

from formiodata.builder import Builder
from formiodata.form import Form
from markupsafe import Markup
from urllib.parse import parse_qs, urlparse

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

UNKNOWN_ODOO_FIELD = 'UNKNOWN Odoo field'


class FormioForm(models.Model):
    _inherit = 'formio.form'

    def formio_component_class_mapping(self):
        """
        This method provides the formiodata.Builder instantiation the
        component_class_mapping keyword argument.

        This method can be implemented in other (formio) modules.
        """
        return {}

    def markupsafe(self, content, extra_replacements=[]):
        """ Escape characters so it is safe to use in HTML and XML
        :param extra_replacements
        """
        replacements = [['\n', '<br/>']]
        replacements += extra_replacements
        for rep in replacements:
            content = content.replace(rep[0], rep[1])
        return Markup(content)

    def __getattr__(self, name):
        if name == '_formio':
            # TODO implement caching on the model object
            # self._cache or self.env.cache API only works for model fields, not Python attr.

            # if '_formio' not in self.__dict__:
            no_cache = True
            if no_cache:
                context = self._context
                if 'lang' in context:
                    lang = context['lang']
                elif 'lang' not in context and 'uid' in context:
                    lang = self.env['res.users'].browse(context['uid']).lang
                elif 'lang' not in context and 'uid' not in context:
                    lang = self.write_uid.lang
                else:
                    raise UserError("The form can't be loaded. No (user) language was set.")

                component_class_mapping = self.formio_component_class_mapping()
                res_lang = self.env['res.lang'].search([('code', '=', lang)], limit=1)
                builder_obj = Builder(
                    self.builder_id.schema,
                    language=res_lang.iso_code,
                    component_class_mapping=component_class_mapping,
                    i18n=self.builder_id.i18n_translations())

                if self.submission_data is False:
                    # HACK masquerade empty Form object
                    # TODO implement caching on the model object
                    # self._formio = Form('{}', builder_obj)
                    form = Form(
                        "{}",
                        builder_obj,
                        date_format=res_lang.date_format,
                        time_format=res_lang.time_format,
                    )
                else:
                    # TODO implement caching on the model object
                    # self._formio = Form(self.submission_data, builder_obj)
                    form = Form(
                        self.submission_data,
                        builder_obj,
                        date_format=res_lang.date_format,
                        time_format=res_lang.time_format,
                    )
                return form
        else:
            return self.__getattribute__(name)

    def _component_selectboxes_data_url_values_labels(self, component):
        """Generate selectboxesComponent value_labels when the Data
        Source Type is URL and the URL is relative (this Odoo instance).

        Similar like the formio-data (library) selectboxesCompopnent
        does, with the default Values Data Source Type.
        """
        url = component.raw['data']['url']
        o = urlparse(url)
        values_labels = {}
        if not o.netloc:
            qs = parse_qs(url)
            model = qs.get('model')
            if model and component.value:
                model = model[0]
                model_obj = self.env[model]
                # values
                value_field = qs.get('value_field')
                if value_field:
                    value_field = value_field[0]
                else:
                    value_field = 'id'
                if model_obj._fields[value_field] == 'integer':
                    values = {int(k): v for k, v in component.value.items()}
                else:
                    values = {k: v for k, v in component.value.items()}
                # label, sort
                label = qs.get('label_field')[0]
                sort = qs.get('sort')
                if sort:
                    sort = sort[0]
                else:
                    sort = model_obj._order + ', id'
                # query records
                domain = [(value_field, 'in', list(values.keys()))]
                records = model_obj.sudo().search(domain, order=sort)
                for rec in records:
                    vals = {
                        'label': rec[label],
                        'value': values[rec[value_field]],
                    }
                    values_labels[rec[value_field]] = vals
        return values_labels
