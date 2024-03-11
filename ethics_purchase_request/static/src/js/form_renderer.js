odoo.define('ethics_purchase_request.form_renderer', function (require) {
"use strict";

var FormRenderer = require('web.FormRenderer');
var FormController = require('web.FormController');
var FormView = require('web.FormView');
var viewRegistry = require('web.view_registry');
var core = require('web.core');

var MyFormController = FormController.extend({
        _updateButtons: function () {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                if (this.renderer.state.data.state == 'draft'){
                    this.$buttons.find('.o_form_button_edit').show();
                }
                else if(this.renderer.state.data.state == 'waiting_for_approver'){
                    this.$buttons.find('.o_form_button_edit').show();
                }
                else {
                    this.$buttons.find('.o_form_button_edit').hide();
                }
            }
        },

    });

    var MyFormView = FormView.extend({
        config: _.extend({}, FormView.prototype.config, {
            Controller: MyFormController,
        }),
    });
    viewRegistry.add('readonly_form_state', MyFormView);

});
