# Changelog

## 16.0.2.3.1

Implement `formio.form` model method `_component_selectboxes_data_url_values_labels`.
It generates a similar datastructure like the formio-data (library) `selectboxesCompopnent` getter `value_labels` does, with the default Values as Data Source Type.
However this method generates `selectboxesComponent` property `value_labels`, when the Data Source Type is URL and the URL is relative (this Odoo instance).

## 16.0.2.3

Add `formio.form` `markupsafe()` instance method to escape components, eg: content, html, textarea.

## 16.0.2.2

Add `component_class_mapping` feature to `formio.builder` model
`_formio` its `getattr` method.

## 16.0.2.1

Improve the `component_class_mapping` feature introduced in previous version `16.0.2.0 `.\

Reading from the `context` requires this `component_class_mapping` to be set by every `formio.form` model instantiation.\
This coverage can't be guaranteed, so the context implementation is removed again.

### Solution (new style)

Instead this version (change) adds the method `formio_component_class_mapping` in the `formio.form` model.\
This method can be extended (in modules) where a `component_class_mapping` is applicable.

Example code:

```python
class FormioForm(models.Model):
    _inherit = 'formio.form'

    def formio_component_class_mapping(self):
        """
        This method provides the formiodata.Builder instatiation the
        component_class_mapping keyword argument.
        """
        component_class_mapping = super().formio_component_class_mapping()
        component_class_mapping['nova_editgrid'] = 'editgrid'
        return component_class_mapping
```

## 16.0.2.0

Ability to set the `formiodata.Builder` instantiation its `component_class_mapping` property.\
This can be provided as a Dictionary on the `formio.form` its `context`, by the keyword argument `formio_component_class_mapping`.

Example:

```python
component_class_mapping = {'nova_editgrid': 'editgrid'}

form = (
    self.env["formio.form"]
    .with_context(formio_component_class_mapping=component_class_mapping)
    .get_form(uuid, 'read')
)
```

More info: https://github.com/novacode-nl/python-formio-data \
Checkout the README and unittest (file): `tests/test_component_class_mapping.py`

## 16.0.1.1

Fix `formiodata.Builder` language determination by IETF-code instead of ISO.

## 16.0.1.0

Initial release.
