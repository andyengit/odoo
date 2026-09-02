# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('-at_install', 'post_install', 'post_install_l10n')
class TestVeChartTemplate(AccountTestInvoicingCommon):
    """Structural checks on the Venezuelan chart of accounts.

    These assert the properties an installed chart must hold to be usable:
    a populated P&L, reconciliation limited to the accounts that need it,
    the accounts the template promises through its own prefixes, and no
    account autocreated outside the chart's code length.
    """

    @classmethod
    def setUpClass(cls, chart_template_ref='ve'):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company = cls.company_data['company']
        cls.accounts = cls.env['account.account'].search([
            ('company_id', '=', cls.company.id),
        ])

    def _codes(self, prefix):
        return self.accounts.filtered(lambda a: a.code.startswith(prefix))

    def test_code_digits(self):
        """Every account uses the chart's declared code length."""
        wrong = self.accounts.filtered(lambda a: len(a.code) != 7)
        self.assertFalse(
            wrong,
            "accounts not using 7 digits: %s" % wrong.mapped(lambda a: '%s %s' % (a.code, a.name)),
        )

    def test_profit_and_loss_is_populated(self):
        """Income and expense accounts must not be typed as assets."""
        for account_type in ('income', 'expense'):
            self.assertTrue(
                self.accounts.filtered(lambda a: a.account_type == account_type),
                "no account of type %s" % account_type,
            )
        # A chart that types its liabilities as current assets produces a
        # balance sheet where payables never appear.
        self.assertTrue(
            self.accounts.filtered(lambda a: a.account_type == 'liability_current'),
            "no liability_current account",
        )

    def test_current_assets_are_not_the_whole_chart(self):
        """Guard against the single-type chart the module used to ship."""
        current = self.accounts.filtered(lambda a: a.account_type == 'asset_current')
        self.assertLess(
            len(current), len(self.accounts) / 2,
            "more than half of the chart is typed asset_current",
        )
        self.assertGreaterEqual(
            len(set(self.accounts.mapped('account_type'))), 12,
            "the chart uses too few account types to produce meaningful reports",
        )

    def test_reconcile_is_not_set_everywhere(self):
        """Income, expense and equity accounts are never reconcilable."""
        wrong = self.accounts.filtered(lambda a: a.reconcile and a.account_type in (
            'income', 'income_other', 'expense', 'expense_direct_cost',
            'expense_depreciation', 'equity', 'equity_unaffected',
        ))
        self.assertFalse(
            wrong,
            "reconcilable P&L or equity accounts: %s" % wrong.mapped('code'),
        )

    def test_unaffected_earnings_account_exists(self):
        """Without it the loader autocreates one outside the chart."""
        self.assertTrue(
            self.accounts.filtered(lambda a: a.account_type == 'equity_unaffected'),
            "no equity_unaffected account, so one is autocreated with a "
            "hardcoded 999999 code",
        )

    def test_declared_prefixes_have_accounts(self):
        """The prefixes the template declares must resolve to real accounts."""
        for field in ('bank_account_code_prefix', 'cash_account_code_prefix',
                      'transfer_account_code_prefix'):
            prefix = self.company[field]
            self.assertTrue(prefix, "%s is not set" % field)
            self.assertTrue(
                self._codes(prefix),
                "%s is %s but no account starts with it" % (field, prefix),
            )

    def test_utility_accounts_come_from_the_chart(self):
        """None of the utility accounts is autocreated by the loader.

        ``_setup_utility_bank_accounts`` creates these in English, two of
        them under a hardcoded ``999`` prefix, whenever the template leaves
        the corresponding company field empty.
        """
        for field in (
            'account_journal_suspense_account_id',
            'account_journal_payment_debit_account_id',
            'account_journal_payment_credit_account_id',
            'account_journal_early_pay_discount_gain_account_id',
            'account_journal_early_pay_discount_loss_account_id',
            'default_cash_difference_income_account_id',
            'default_cash_difference_expense_account_id',
            'transfer_account_id',
        ):
            account = self.company[field]
            self.assertTrue(account, "%s is not set by the template" % field)
            self.assertEqual(
                len(account.code), 7,
                "%s points at %s, which is outside the chart's code length"
                % (field, account.code),
            )

    def test_accumulated_depreciation_per_asset(self):
        """Each depreciable asset class carries its own accumulated account.

        Land and construction in progress are not depreciated, so the
        accumulated accounts are expected to be two fewer than the cost ones.
        """
        cost = self._codes('1501')
        accumulated = self._codes('1502')
        self.assertTrue(accumulated, "no accumulated depreciation accounts")
        self.assertEqual(
            len(accumulated), len(cost) - 2,
            "expected one accumulated depreciation account per depreciable "
            "asset class: %s cost accounts, %s accumulated"
            % (len(cost), len(accumulated)),
        )

    def test_vat_posts_to_a_single_account_per_direction(self):
        """Every VAT rate posts to the same account, the rate tells them apart.

        The purchase and sales VAT books aggregate on one account each, so a
        chart that splits VAT per rate cannot produce them without extra
        mapping.
        """
        taxes = self.env['account.tax'].search([
            ('company_id', '=', self.company.id),
            ('amount', '>', 0),
            ('amount_type', '=', 'percent'),
        ])
        self.assertTrue(taxes, "no percentage taxes loaded")
        for tax_use in ('sale', 'purchase'):
            accounts = taxes.filtered(lambda t: t.type_tax_use == tax_use) \
                .invoice_repartition_line_ids \
                .filtered(lambda r: r.repartition_type == 'tax') \
                .account_id
            self.assertEqual(
                len(accounts), 1,
                "%s VAT posts to %s accounts, expected 1: %s"
                % (tax_use, len(accounts), accounts.mapped('code')),
            )

    def test_general_vat_rate_exists(self):
        """The rate in force must be available out of the box."""
        rates = self.env['account.tax'].search([
            ('company_id', '=', self.company.id),
            ('type_tax_use', '=', 'sale'),
        ]).mapped('amount')
        self.assertIn(16.0, rates, "the 16%% general VAT rate is missing")

    def test_company_defaults_use_the_general_rate(self):
        """A new order must not default to a repealed rate."""
        for field in ('account_sale_tax_id', 'account_purchase_tax_id'):
            tax = self.company[field]
            self.assertTrue(tax, "%s is not set" % field)
            self.assertEqual(
                tax.amount, 16.0,
                "%s defaults to %s%%, which is not the rate in force"
                % (field, tax.amount),
            )
