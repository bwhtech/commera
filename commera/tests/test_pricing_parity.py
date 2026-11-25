"""M4 + R2-2: Parametrized parity tests across all four parallel pricing/preview implementations."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import add_days, flt, today

from commera.base_prices import (
	can_use_direct_item_price,
	has_non_stock_sales_uom,
	has_template_item_prices,
	public_rates_query,
)
from commera.card_prices import size_prices_query
from commera.cart_prices import fetch_batched_line_prices, get_line_price
from commera.discounts.preview import get_preview_quotation
from commera.localization import pin_localization, resolve
from commera.localization.market_prices import MarketPrices
from commera.localization.markets import delete_cached_rows
from commera.tests import get_test_configurator
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_markets import use_markets


class TestPricingPathParity(IntegrationTestCase):
	"""Force both fast and full paths over identical fixtures and assert exact equivalence."""

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		self.addCleanup(frappe.local.request_cache.clear)
		self.suffix = frappe.generate_hash(length=8).upper()
		self.company = frappe.get_cached_value(
			"Commera Settings", "Commera Settings", "company"
		) or frappe.defaults.get_global_default("company")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "INR"
		self.sale_pl = self._make_price_list("Sale", self.currency)
		self.compare_pl = self._make_price_list("Compare", self.currency)
		self.configurator = get_test_configurator()
		self.item_group = (
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": f"ZZ Parity Group {self.suffix}",
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

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

	def _make_item(
		self,
		code: str,
		*,
		stock_uom: str = "Nos",
		sales_uom: str | None = None,
		uoms: list[dict] | None = None,
		has_variants: int = 0,
		variant_of: str | None = None,
		attributes: list[dict] | None = None,
	) -> str:
		payload = {
			"doctype": "Item",
			"item_code": f"ZZ-PAR-{code}-{self.suffix}",
			"item_name": f"Parity {code}",
			"item_group": self.item_group,
			"stock_uom": stock_uom,
			"sales_uom": sales_uom,
			"is_stock_item": 0,
			"has_variants": has_variants,
		}
		if variant_of:
			payload["variant_of"] = variant_of
		if attributes:
			payload["attributes"] = attributes
		if uoms:
			payload["uoms"] = uoms
		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
		return doc.name

	def _make_price(self, item_code: str, price_list: str, rate: float, *, valid_from=None, uom=None) -> str:
		payload = {
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": rate,
			"valid_from": valid_from or today(),
		}
		if uom is not None:
			payload["uom"] = uom
		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
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
				"item_group": self.item_group,
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

	def test_non_stock_sales_uom_parity_across_base_cart_and_preview(self):
		"""R2-2: sales_uom != stock_uom disables direct path and matches ERPNext UOM conversion."""
		if not frappe.db.exists("UOM", "Box"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Box", "enabled": 1}).insert(
				ignore_permissions=True
			)
		item_code = self._make_item(
			"UOM",
			stock_uom="Nos",
			sales_uom="Box",
			uoms=[{"uom": "Box", "conversion_factor": 12}],
		)
		self._make_price(item_code, self.sale_pl, 10, uom="Nos")

		self.assertTrue(has_non_stock_sales_uom())
		self.assertFalse(can_use_direct_item_price())

		# base_prices converts stock UOM price (10/Nos) to sales UOM (120/Box).
		rows = public_rates_query([self.sale_pl], [item_code]).run(as_dict=True)
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0].rate, 2), 120.0)

		# cart_prices batched matches ERPNext get_price_list_rate_for (120/Box).
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
		batched = fetch_batched_line_prices(quotation, quotation.items, prices)
		fast_line = get_line_price(quotation, quotation.items[0], prices, batched=batched)
		erp_line = get_line_price(quotation, quotation.items[0], prices, batched=None)
		self.assertEqual(fast_line, erp_line)
		self.assertEqual(flt(fast_line[1], 2), 120.0)

		# discounts/preview fast vs set_missing_values agree on rate, total, and stock_qty.
		settings = frappe.get_doc("Commera Settings")
		settings.sale_price_list = self.sale_pl
		settings.default_price_list = self.compare_pl
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		with patch("commera.discounts.preview.can_fast_price_preview", return_value=True):
			fast_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])
		with patch("commera.discounts.preview.can_fast_price_preview", return_value=False):
			full_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])

		self.assertEqual(flt(fast_q.items[0].rate, 2), flt(full_q.items[0].rate, 2))
		self.assertEqual(flt(fast_q.items[0].conversion_factor, 4), flt(full_q.items[0].conversion_factor, 4))
		self.assertEqual(flt(fast_q.items[0].stock_qty, 4), flt(full_q.items[0].stock_qty, 4))
		self.assertEqual(flt(fast_q.grand_total, 2), flt(full_q.grand_total, 2))

	def test_template_priced_variant_parity_across_base_cart_and_preview(self):
		"""R2-2: template-priced variant disables direct path and matches ERPNext fallback."""
		template_code = self._make_item("TPL")
		variant_code = self._make_item("VAR")
		self._make_price(template_code, self.sale_pl, 65)
		frappe.db.set_value("Item", template_code, "has_variants", 1)
		frappe.db.set_value("Item", variant_code, "variant_of", template_code)
		frappe.clear_document_cache("Item", template_code)
		frappe.clear_document_cache("Item", variant_code)

		self.assertTrue(has_template_item_prices())
		self.assertFalse(can_use_direct_item_price())

		rows = public_rates_query([self.sale_pl], [variant_code]).run(as_dict=True)
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0].rate, 2), 65.0)

		prices = MarketPrices("primary", True, self.sale_pl, self.compare_pl, self.currency)
		quotation = frappe.new_doc("Quotation")
		quotation.update(
			{
				"company": self.company,
				"quotation_to": "Customer",
				"transaction_date": today(),
				"items": [{"item_code": variant_code, "qty": 3}],
			}
		)
		batched = fetch_batched_line_prices(quotation, quotation.items, prices)
		fast_line = get_line_price(quotation, quotation.items[0], prices, batched=batched)
		erp_line = get_line_price(quotation, quotation.items[0], prices, batched=None)
		self.assertEqual(fast_line, (self.sale_pl, 65.0))
		self.assertEqual(fast_line, erp_line)

		settings = frappe.get_doc("Commera Settings")
		settings.sale_price_list = self.sale_pl
		settings.default_price_list = self.compare_pl
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		with patch("commera.discounts.preview.can_fast_price_preview", return_value=True):
			fast_q = get_preview_quotation([{"item_code": variant_code, "qty": 3}])
		with patch("commera.discounts.preview.can_fast_price_preview", return_value=False):
			full_q = get_preview_quotation([{"item_code": variant_code, "qty": 3}])

		self.assertEqual(flt(fast_q.grand_total, 2), flt(full_q.grand_total, 2))
		self.assertEqual(flt(fast_q.items[0].rate, 2), 65.0)

	def test_secondary_currency_market_preview_and_pricing_parity(self):
		"""R2-2: secondary-currency market (AED) matches across fast preview and ERPNext set_missing_values."""
		use_storefront_languages(self, "en", published=("en",))
		use_markets(self)
		mkt_currency = "USD" if self.currency == "AED" else "AED"
		mkt_sale = self._make_price_list(f"MktSale-{mkt_currency}", mkt_currency)
		mkt_compare = self._make_price_list(f"MktCmp-{mkt_currency}", mkt_currency)
		if not frappe.db.exists(
			"Currency Exchange", {"from_currency": mkt_currency, "to_currency": self.currency}
		):
			frappe.get_doc(
				{
					"doctype": "Currency Exchange",
					"date": today(),
					"from_currency": mkt_currency,
					"to_currency": self.currency,
					"exchange_rate": 22.5,
					"for_selling": 1,
				}
			).insert(ignore_permissions=True)

		item_code = self._make_item("MKT")
		self._make_price(item_code, mkt_sale, 40)
		self._make_price(item_code, mkt_compare, 55)

		handle = f"zzmkt{self.suffix.lower()[:4]}"
		mkt = frappe.get_doc(
			{
				"doctype": "Commera Market",
				"handle": handle,
				"market_name": f"ZZ Market {self.suffix}",
				"enabled": 1,
				"currency": mkt_currency,
				"sale_price_list": mkt_sale,
				"compare_at_price_list": mkt_compare,
				"default_language": "en",
				"countries": [{"country": "Oman"}],
				"languages": [{"language": "en"}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(delete_cached_rows)
		delete_cached_rows()

		loc = resolve("/", country="OM")[0]
		self.assertEqual(loc.market.handle, mkt.name)
		with pin_localization(loc):
			with patch("commera.discounts.preview.can_fast_price_preview", return_value=True):
				fast_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])
			with patch("commera.discounts.preview.can_fast_price_preview", return_value=False):
				full_q = get_preview_quotation([{"item_code": item_code, "qty": 2}])

		self.assertEqual(fast_q.currency, mkt_currency)
		self.assertEqual(flt(fast_q.grand_total, 2), flt(full_q.grand_total, 2))
		self.assertEqual(flt(fast_q.base_grand_total, 2), flt(full_q.base_grand_total, 2))
		self.assertEqual(flt(fast_q.conversion_rate, 4), flt(full_q.conversion_rate, 4))

	def test_fast_preview_matches_erpnext_set_missing_values_with_taxes(self):
		"""M4 + R2-2: fast preview matches ERPNext set_missing_values for plain, exclusive tax, and inclusive tax."""
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
		self.assertTrue(account, f"No Tax/Liability account found for company {self.company}")

		for inclusive in (None, 0, 1):
			with self.subTest(inclusive=inclusive):
				template_name = None
				if inclusive is not None:
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

				if inclusive is not None:
					self.assertTrue(fast_q.taxes, "tax subtest must exercise non-empty taxes")
				self.assertEqual(flt(fast_q.total, 2), flt(full_q.total, 2))
				self.assertEqual(flt(fast_q.net_total, 2), flt(full_q.net_total, 2))
				self.assertEqual(flt(fast_q.grand_total, 2), flt(full_q.grand_total, 2))
				self.assertEqual(flt(fast_q.items[0].rate, 2), flt(full_q.items[0].rate, 2))
				self.assertEqual(flt(fast_q.items[0].net_amount, 2), flt(full_q.items[0].net_amount, 2))
