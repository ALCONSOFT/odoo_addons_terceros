# dev_petty_cash/tests/test_petty_cash_expense.py
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)

class TestPettyCashExpenseFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestPettyCashExpenseFlow, cls).setUpClass()

        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True)) # Disable tracking for faster tests

        # Company
        cls.company = cls.env.ref('base.main_company')
        cls.currency_usd = cls.env.ref('base.USD')
        cls.company.currency_id = cls.currency_usd

        # Create Products
        ProductProduct = cls.env['product.product']
        cls.product_stockable = ProductProduct.create({
            'name': 'Test Stockable Product',
            'type': 'product',
            'standard_price': 100.0,
            'categ_id': cls.env.ref('product.product_category_all').id,
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'uom_po_id': cls.env.ref('uom.product_uom_unit').id,
        })
        cls.product_service = ProductProduct.create({
            'name': 'Test Service Product',
            'type': 'service',
            'standard_price': 50.0,
            'categ_id': cls.env.ref('product.product_category_all').id,
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'uom_po_id': cls.env.ref('uom.product_uom_unit').id,
        })

        # Create Supplier Partner
        cls.supplier = cls.env['res.partner'].create({
            'name': 'Test Supplier',
            'supplier_rank': 1,
        })

        # Create Employee
        admin_user = cls.env.ref('base.user_admin')
        if not admin_user.employee_ids:
            cls.employee = cls.env['hr.employee'].create({
                'name': 'Admin Employee Test', # Ensure unique name if tests run multiple times
                'user_id': admin_user.id,
                'company_id': cls.company.id,
            })
        else:
            cls.employee = admin_user.employee_ids[0]

        # Find or create necessary accounts
        AccountAccount = cls.env['account.account']
        cls.cash_account = AccountAccount.search([
            ('company_id', '=', cls.company.id), ('account_type', '=', 'asset_cash')
        ], limit=1)
        if not cls.cash_account:
            cls.cash_account = AccountAccount.create({
                'name': 'Test Cash Account', 'code': 'TCASH01',
                'account_type': 'asset_cash', 'company_id': cls.company.id,
            })

        cls.expense_account_generic = AccountAccount.search([
            ('company_id', '=', cls.company.id), ('account_type', '=', 'expense')
        ], limit=1)
        if not cls.expense_account_generic:
            cls.expense_account_generic = AccountAccount.create({
                'name': 'Test Generic Expense Acc', 'code': 'TEXPGEN01',
                'account_type': 'expense', 'company_id': cls.company.id,
            })

        # Assign expense account to product category if not set (helps ensure action_validate can complete)
        product_category = cls.env.ref('product.product_category_all')
        if not product_category.property_account_expense_categ_id:
            product_category.property_account_expense_categ_id = cls.expense_account_generic


        # Create Petty Cash Journal
        cls.petty_journal = cls.env['account.journal'].create({
            'name': 'Test Petty Cash Journal', 'type': 'cash', 'code': 'TPCJ1',
            'is_petty_cash': True, 'company_id': cls.company.id,
            'default_account_id': cls.cash_account.id,
        })

        # Create Payment Journal
        cls.payment_journal = cls.env['account.journal'].create({
            'name': 'Test Payment Journal Bank', 'type': 'bank', 'code': 'TBNK1',
            'company_id': cls.company.id, 'default_account_id': cls.cash_account.id, # Or a bank account
        })

        # Stock Locations
        cls.stock_location = cls.env.ref('stock.stock_location_stock')
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')

        # Picking types
        cls.picking_type_in = cls.env.ref('stock.picking_type_in')
        cls.picking_type_out = cls.env.ref('stock.picking_type_out')


    def setUp(self):
        super(TestPettyCashExpenseFlow, self).setUp()
        # Create a fresh petty cash expense record for each test
        self.petty_expense = self.env['petty.cash.expense'].create({
            'employee_id': self.employee.id,
            'petty_journal_id': self.petty_journal.id,
            'payment_journal_id': self.payment_journal.id,
            'date': date.today(),
            'company_id': self.company.id,
            'currency_id': self.currency_usd.id,
        })

    def _create_stock_move(self, product, quantity, location_from, location_to, origin_ref):
        picking_type = self.picking_type_in if location_to == self.stock_location else self.picking_type_out
        move = self.env['stock.move'].create({
            'name': product.name, 'product_id': product.id,
            'product_uom_qty': quantity, 'product_uom': product.uom_id.id,
            'location_id': location_from.id, 'location_dest_id': location_to.id,
            'origin': origin_ref, 'state': 'draft', 'picking_type_id': picking_type.id
        })
        move._action_confirm()
        move._action_assign()
        for ml in move.move_line_ids:
            ml.qty_done = quantity
        move._action_done()
        return move

    # Test methods
    def test_01_stockable_product_valid_justification_purchase(self):
        _logger.info("Running test_01_stockable_product_valid_justification_purchase")
        move_ref = 'IN/T01/STOCK_VALID'
        stock_move = self._create_stock_move(self.product_stockable, 1, self.supplier_location, self.stock_location, move_ref)
        self.assertEqual(stock_move.state, 'done', "Stock move should be done.")

        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'note_expense': 'Inv T01', 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'INVT01',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': 100.0,
                    'inventory_justification_ref': move_ref, 'is_credit_note_line': False,
                })], 'tax_amount': 0,
            })]
        })
        try:
            self.petty_expense.action_confirm() # Confirm first
            self.petty_expense.action_validate()
        except ValidationError as e:
            self.fail(f"Validation failed unexpectedly: {e}")
        self.assertEqual(self.petty_expense.state, 'done', "Expense state should be done.")

    def test_02_stockable_product_no_ref(self):
        _logger.info("Running test_02_stockable_product_no_ref")
        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'INVT02',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': 100.0,
                })],
            })]
        })
        self.petty_expense.action_confirm()
        with self.assertRaisesRegex(ValidationError, "Inventory Justification Ref is required"):
            self.petty_expense.action_validate()

    def test_03_stockable_product_ref_no_move(self):
        _logger.info("Running test_03_stockable_product_ref_no_move")
        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                 'account_id': self.expense_account_generic.id, 'invoice_number': 'INVT03',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': 100.0,
                    'inventory_justification_ref': 'NONEXISTENT/T03/REF',
                })],
            })]
        })
        self.petty_expense.action_confirm()
        with self.assertRaisesRegex(ValidationError, "Inventory justification missing for stockable product"):
            self.petty_expense.action_validate()

    def test_04_stockable_credit_note_valid_justification(self):
        _logger.info("Running test_04_stockable_credit_note_valid_justification")
        move_ref = 'OUT/T04/STOCK_CN_VALID'
        stock_move = self._create_stock_move(self.product_stockable, 1, self.stock_location, self.supplier_location, move_ref)
        self.assertEqual(stock_move.state, 'done', "Stock move for credit note should be done.")

        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'CNT04',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': -100.0,
                    'inventory_justification_ref': move_ref, 'is_credit_note_line': True,
                })],
            })]
        })
        try:
            self.petty_expense.action_confirm()
            self.petty_expense.action_validate()
        except ValidationError as e:
            self.fail(f"Validation failed unexpectedly for credit note: {e}")
        self.assertEqual(self.petty_expense.state, 'done', "Expense state for credit note should be done.")

    def test_05_stockable_credit_note_no_ref(self):
        _logger.info("Running test_05_stockable_credit_note_no_ref")
        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'CNT05',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': -100.0,
                    'is_credit_note_line': True,
                })],
            })]
        })
        self.petty_expense.action_confirm()
        with self.assertRaisesRegex(ValidationError, "Inventory Justification Ref is required"):
            self.petty_expense.action_validate()

    def test_06_stockable_credit_note_ref_no_move(self):
        _logger.info("Running test_06_stockable_credit_note_ref_no_move")
        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'CNT06',
                'product_lines': [(0, 0, {
                    'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': -100.0,
                    'inventory_justification_ref': 'NONEXISTENT/T06/CNREF', 'is_credit_note_line': True,
                })],
            })]
        })
        self.petty_expense.action_confirm()
        with self.assertRaisesRegex(ValidationError, "Inventory justification missing for stockable product"):
            self.petty_expense.action_validate()

    def test_07_service_product_no_ref_should_pass(self):
        _logger.info("Running test_07_service_product_no_ref_should_pass")
        self.petty_expense.write({
            'expense_lines': [(0, 0, {
                'date_expense': date.today(), 'supplier_id': self.supplier.id,
                'account_id': self.expense_account_generic.id, 'invoice_number': 'INVT07_SERVICE',
                'product_lines': [(0, 0, {
                    'product_id': self.product_service.id, 'quantity': 1, 'price_unit': 50.0,
                })],
            })]
        })
        try:
            self.petty_expense.action_confirm()
            self.petty_expense.action_validate()
        except ValidationError as e:
            self.fail(f"Validation failed for service product: {e}")
        self.assertEqual(self.petty_expense.state, 'done', "Expense state for service product should be done.")

    def test_08_amount_calculation(self):
        _logger.info("Running test_08_amount_calculation")
        expense_line_vals = {
            'date_expense': date.today(), 'supplier_id': self.supplier.id,
            'account_id': self.expense_account_generic.id, 'invoice_number': 'INVT08_AMOUNTS',
            'product_lines': [
                (0, 0, {'product_id': self.product_service.id, 'quantity': 2, 'price_unit': 50.0}),
                (0, 0, {'product_id': self.product_stockable.id, 'quantity': 1, 'price_unit': 75.0,
                         'inventory_justification_ref': 'dummy_T08_calc_test'})
            ], 'tax_amount': 17.5, # tax_amount is manually set for this test case
        }
        # Create the expense line as part of the petty_expense to ensure computes are triggered
        self.petty_expense.write({'expense_lines': [(0,0, expense_line_vals)]})
        created_expense_line = self.petty_expense.expense_lines[0]

        # Assuming product_lines are created and their subtotals are computed
        self.assertEqual(created_expense_line.product_lines[0].price_subtotal, 100.0, "Subtotal for product line 1")
        self.assertEqual(created_expense_line.product_lines[1].price_subtotal, 75.0, "Subtotal for product line 2")

        # Check computed invoice_amount (sum of product_lines subtotals)
        self.assertEqual(created_expense_line.invoice_amount, 175.0, "Invoice amount on expense line")

        # Check computed amount (invoice_amount + tax_amount)
        self.assertEqual(created_expense_line.amount, 192.5, "Total amount on expense line")
