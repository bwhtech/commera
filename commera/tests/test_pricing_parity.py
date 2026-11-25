"""M4: Parametrized parity tests across all four parallel pricing/preview implementations."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import add_days, flt, today

from commera.base_prices import public_rates_query
from commera.card_prices import size_prices_query
from commera.cart_prices import fetch_batched_line_prices, get_line_price
from commera.discounts.preview import get_preview_quotation
from commera.localization.market_prices import MarketPrices
from commera.tests import get_test_configurator


class TestPricingPathParity(IntegrationTestCase):
	"""Force both fast and full paths over identical fixtures and assert exact equivalence."""

	def setUp(self):
		super().setUp()
		self.suffix = frappe.generate_hash(length=8).upper()
		self.company = frappe.get_cached_value(
			"Commera Settings", "Commera Settings", "company"
		) or frappe.defaults.get_global_default("company")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "INR"
		self.sale_pl = self._make_price_list("Sale", self.currency)
		self.compare_pl = self._make_price_list("Compare", self.currency)
		self.configurator = get_test_configurator()

	def _make_price_list(self, label: str, currency: str) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": f"ZZ Parity {label} {self.suffix}",
				"currency": currency,
				"selling": 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _make_item(self, code: str, *, stock_uom: str = "Nos", sales_uom: str | None = None) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"ZZ-PAR-{code}-{self.suffix}",
				"item_name": f"Parity {code}",
				"item_group": "All Item Groups",
				"stock_uom": stock_uom,
				"sales_uom": sales_uom,
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _make_price(self, item_code: str, price_list: str, rate: float, *, valid_from=None) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"valid_from": valid_from or today(),
			}
		).insert(ignore_permissions=True)
		return doc.name

	def test_base_prices_direct_matches_ranked_query(self):
		priced = self._make_item("BP1")
		unpriced = self._make_item("BP2")
		self._make_price(priced, self.sale_pl, 75)
		self._make_price(priced, self.compare_pl, 100)

		with patch("commera.base_prices.can_use_direct_item_price", return_value=True):
			direct = public_rates_query([self.sale_pl, self.compare_pl], [priced, unpriced]).run(as_dict=True)
		with patch("commera.base_prices.can_use_direct_item_price", return_value=False):
			ranked = public_rates_query([self.sale_pl, self.compare_pl], [priced, unpriced]).run(as_dict=True)

		def key(rows):
			return sorted((r.item_code, r.price_list, flt(r.rate), r.price_name) for r in rows)

		self.assertEqual(key(direct), key(ranked))

	def test_card_prices_direct_matches_ranked_including_unpriced_sizes(self):
		"""M4: direct size_prices_query must LEFT JOIN prices so unpriced sizes are not dropped."""
		priced_size = self._make_item("SZ1")
		unpriced_size = self._make_item("SZ2")
		self._make_price(priced_size, self.sale_pl, 90)
		self._make_price(priced_size, self.compare_pl, 120)

		variant = frappe.get_doc(
			{
				"doctype": "Style Attribute Variant",
				"configurator": self.configurator,
				"item_style": priced_size,
				"item_group": "All Item Groups",
				"attribute_value": f"V-{self.suffix}",
				"display_name": f"Parity Card {self.suffix}",
				"route": f"zz-par-card-{self.suffix.lower()}",
				"is_published": 1,
				"sizes": [
					{"size": "S", "item_code": priced_size},
					{"size": "L", "item_code": unpriced_size},
				],
			}
		).insert(ignore_permissions=True)

		with patch("commera.card_prices.can_use_direct_item_price", return_value=True):
			direct = size_prices_query(self.sale_pl, self.compare_pl, [variant.name]).run(as_dict=True)
		with patch("commera.card_prices.can_use_direct_item_price", return_value=False):
			ranked = size_prices_query(self.sale_pl, self.compare_pl, [variant.name]).run(as_dict=True)

		def norm(rows):
			tuples = [
				(
					r.parent,
					None if r.sale is None else flt(r.sale),
					None if r.compare_at is None else flt(r.compare_at),
					None if r.size_price is None else flt(r.size_price),
					None if r.lowest_price is None else flt(r.lowest_price),
				)
				for r in rows
			]
			return sorted(tuples, key=lambda t: tuple((x is None, 0 if x is None else x) for x in t))

		self.assertEqual(len(direct), 2)
		self.assertEqual(norm(direct), norm(ranked))

	def test_cart_prices_batched_matches_erpnext_including_duplicates(self):
		"""M4: batched get_line_price must match ERPNext get_price_list_rate_for across duplicate rows."""
		item_code = self._make_item("DUP")
		self._make_price(item_code, self.sale_pl, 120, valid_from=add_days(today(), -10))
		self._make_price(item_code, self.sale_pl, 95, valid_from=add_days(today(), -1))
		self._make_price(item_code, self.compare_pl, 150)

		prices = MarketPrices("primary", True, self.sale_pl, self.compare_pl, self.currency)
		quotation = frappe.new_doc("Quotation")
		quotation.update(
			{
				"company": self.company,
				"quotation_to": "Customer",
				"transaction_date": today(),
				"items": [{"item_code": item_code, "qty": 2}],
			}
		)
		line = quotation.items[0]

		batched = fetch_batched_line_prices(quotation, [line], prices)
		fast_res = get_line_price(quotation, line, prices, batched=batched)
		erp_res = get_line_price(quotation, line, prices, batched=None)

		self.assertEqual(fast_res, (self.sale_pl, 95.0))
		self.assertEqual(fast_res, erp_res)

	def test_fast_preview_matches_erpnext_set_missing_values_with_taxes(self):
		"""M4: fast preview matches ERPNext set_missing_values for plain, exclusive tax, and inclusive tax."""
		item_code = self._make_item("PRV")
		self._make_price(item_code, self.sale_pl, 100)
		settings = frappe.get_doc("Commera Settings")
		settings.sale_price_list = self.sale_pl
		settings.default_price_list = self.compare_pl
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		account = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Tax", "is_group": 0}, "name"
		) or frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Liability", "is_group": 0}, "name"
		)

		for inclusive in (None, 0, 1):
			with self.subTest(inclusive=inclusive):
				template_name = None
				if inclusive is not None and account:
					tpl = frappe.get_doc(
						{
							"doctype": "Sales Taxes and Charges Template",
							"title": f"ZZ Parity Tax {inclusive} {self.suffix}",
							"company": self.company,
							"taxes": [
								{
									"charge_type": "On Net Total",
									"account_head": account,
									"description": "Parity VAT 10%",
									"rate": 10,
									"included_in_print_rate": inclusive,
								}
							],
						}
					).insert(ignore_permissions=True)
					template_name = tpl.name

				def _apply_tax(q, _market, switched=False, tpl_name=template_name):
					if tpl_name:
						q.taxes_and_charges = tpl_name
						q.set("taxes", [])
						for row in frappe.get_doc("Sales Taxes and Charges Template", tpl_name).taxes:
							q.append("taxes", row.as_dict())

				with patch("commera.cart_prices.apply_market_taxes", side_effect=_apply_tax):
					with patch("commera.discounts.preview.can_fast_price_preview", return_value=True):
						fast_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])
					with patch("commera.discounts.preview.can_fast_price_preview", return_value=False):
						full_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])

				self.assertEqual(flt(fast_q.total, 2), flt(full_q.total, 2))
				self.assertEqual(flt(fast_q.net_total, 2), flt(full_q.net_total, 2))
				self.assertEqual(flt(fast_q.grand_total, 2), flt(full_q.grand_total, 2))
				self.assertEqual(flt(fast_q.items[0].rate, 2), flt(full_q.items[0].rate, 2))
				self.assertEqual(flt(fast_q.items[0].net_amount, 2), flt(full_q.items[0].net_amount, 2))
