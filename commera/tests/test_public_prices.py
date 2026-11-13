"""The storefront prices a product only from the Item Price rows ERPNext would use today, and the cart
lets ERPNext price a line from the compare-at list as it prices one from the sale list."""

from pathlib import Path

import frappe
from frappe.utils import add_days, getdate, today

from commera.api.variant_pricing import set_variant_prices
from commera.core import get_party
from commera.discounts.preview import get_preview_quotation
from commera.localization.cart_currency import CartCurrency
from commera.localization.content import SHOP_WIDE
from commera.localization.market_prices import MarketPrices
from commera.sdk import cart as cart_sdk
from commera.sdk import catalog
from commera.search.price_markets import get_price_markets, prices_for_variants
from commera.tests.test_market_cart import MarketCartTestCase

SUMMER_CARD = "themes/summer_theme/components/macros/product_card.html"


class PublicPriceTestCase(MarketCartTestCase):
	def expire(self, item_code, price_list):
		name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
		price = frappe.get_doc("Item Price", name)
		price.update({"valid_from": add_days(today(), -30), "valid_upto": add_days(today(), -1)})
		price.save()

	def make_price(self, item_code, price_list, rate, **fields):
		price = {"doctype": "Item Price", "item_code": item_code, "price_list": price_list}
		return frappe.get_doc({**price, "price_list_rate": rate, **fields}).insert().name

	def sell_in_boxes(self, item_code):
		item = frappe.get_doc("Item", item_code)
		item.append("uoms", {"uom": get_uom("ZZ Box"), "conversion_factor": 10})
		item.sales_uom = "ZZ Box"
		item.save()

	def storefront(self, route):
		"""The product page, the card and the index row of `route` in the store."""
		item_code = self.get_item_code(route)
		name = frappe.db.get_value("Style Attribute Variant", {"route": route})
		product = catalog.get_product(route)
		card = self.get_card(route)
		index = prices_for_variants([name], {name: [{"item_code": item_code}]}, get_price_markets())
		return {
			"product": (product["price"], product["available"]),
			"card": (card["price"], card["compare_at_price"], card["available"]),
			"index": index[name][SHOP_WIDE]["effective_price"],
		}


class TestPublicPriceRows(PublicPriceTestCase):
	def test_an_expired_sale_price_is_no_price(self):
		route = self.make_market_variant("EXPIREDSALE")
		self.expire(self.get_item_code(route), self.sale_price_list)

		self.assertEqual(
			self.storefront(route), {"product": (100, True), "card": (100, None, True), "index": 100}
		)

	def test_a_product_whose_only_price_expired_is_not_for_sale(self):
		route = self.make_priced_variant("EXPIREDONLY", default_rate=100)
		item_code = self.get_item_code(route)
		self.expire(item_code, self.default_price_list)

		view = self.storefront(route)

		self.assertEqual((view["product"], view["card"]), ((None, False), (None, None, False)))
		self.assertEqual(MarketPrices.current().get_unavailable([item_code]), {item_code})
		self.sign_in_shopper()
		with self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
			self.add(item_code)

	def test_a_supplier_price_is_not_the_public_price(self):
		# A supplier row needs a list that is also buying, as when one list serves both.
		frappe.db.set_value("Price List", self.sale_price_list, "buying", 1)
		route = self.make_market_variant("SUPPLIER")
		self.make_price(self.get_item_code(route), self.sale_price_list, 17, supplier=get_supplier())

		self.assertEqual(
			self.storefront(route), {"product": (80, True), "card": (80, 100, True), "index": 80}
		)


class TestCartListRates(PublicPriceTestCase):
	def test_an_expired_sale_line_sells_at_its_compare_at_rate(self):
		route = self.make_market_variant("CARTEXPIRED")
		item_code = self.get_item_code(route)
		self.expire(item_code, self.sale_price_list)
		self.sign_in_shopper()

		line = self.lines(self.add(item_code))[item_code]

		self.assertEqual((line["price"], line["rate"]), (100, 100))

	def test_a_compare_at_line_sells_in_its_sales_uom(self):
		item_code = self.get_item_code(self.make_priced_variant("CARTBOX", default_rate=12))
		self.sell_in_boxes(item_code)
		self.sign_in_shopper()

		priced = self.add(item_code)

		self.assertEqual(self.lines(priced)[item_code]["rate"], 120)
		self.assertEqual(priced["subtotal"], 120)

	def test_a_customer_sale_price_beats_the_compare_at_rate(self):
		item_code = self.get_item_code(self.make_priced_variant("CARTCUSTOMER", default_rate=400))
		self.sign_in_shopper()
		shopper = frappe.session.user
		customer = get_party(shopper).name
		frappe.set_user("Administrator")
		self.make_price(item_code, self.sale_price_list, 250, customer=customer)
		frappe.set_user(shopper)

		line = self.lines(self.add(item_code))[item_code]

		self.assertEqual(line["rate"], 250)


class TestERPNextRowChoice(PublicPriceTestCase):
	def test_a_dated_row_beats_a_newer_undated_row(self):
		route = self.make_priced_variant("DATEDROW", default_rate=120)
		item_code = self.get_item_code(route)
		self.make_price(item_code, self.sale_price_list, 80, valid_from=add_days(today(), -2))
		self.make_price(item_code, self.sale_price_list, 110)

		self.assertEqual(
			self.storefront(route), {"product": (80, True), "card": (80, 120, True), "index": 80}
		)
		self.sign_in_shopper()
		self.assertEqual(self.lines(self.add(item_code))[item_code]["rate"], 80)

	def test_a_variant_without_a_row_takes_its_template_price(self):
		route = self.make_priced_variant("TEMPLATED", default_rate=400)
		item_code = self.get_item_code(route)
		# ERPNext refuses a price on a template, so the template is priced before it has variants.
		template = self.make_item("TEMPLATE")
		self.make_price(template, self.sale_price_list, 275)
		frappe.db.set_value("Item", template, "has_variants", 1)
		frappe.db.set_value("Item", item_code, "variant_of", template)

		self.assertEqual(
			self.storefront(route), {"product": (275, True), "card": (275, 400, True), "index": 275}
		)
		self.sign_in_shopper()
		self.assertEqual(self.lines(self.add(item_code))[item_code]["rate"], 275)

	def test_a_product_shows_the_price_of_its_sales_uom(self):
		route = self.make_priced_variant("SHOWBOX", default_rate=12)
		item_code = self.get_item_code(route)
		self.sell_in_boxes(item_code)

		product, card = catalog.get_product(route), self.get_card(route)

		self.assertEqual(
			(product["price"], product["unit"], product["variants"][0]["unit"]), (120, "ZZ Box", "ZZ Box")
		)
		self.assertEqual((card["price"], card["unit"]), (120, "ZZ Box"))
		self.assertEqual(self.storefront(route)["index"], 120)
		self.assertEqual(catalog.get_items([item_code])[item_code]["unit"], "ZZ Box")

	def test_a_sale_row_in_packs_refuses_a_quantity_it_does_not_fit(self):
		route = self.make_priced_variant("PACKED", default_rate=300)
		item_code = self.get_item_code(route)
		self.make_price(item_code, self.sale_price_list, 240, packing_unit=10)
		self.sign_in_shopper()

		priced = cart_sdk.add_lines([{"item_code": item_code, "qty": 10}])

		self.assertEqual(self.lines(priced)[item_code]["rate"], 240)
		self.assertEqual(catalog.get_product(route)["price"], 240)
		with self.assertRaisesRegex(frappe.ValidationError, "multiples of 10"):
			self.add(item_code)


class TestCartDate(PublicPriceTestCase):
	def preview(self, item_code, on_date):
		dates = {"transaction_date": on_date, "valid_till": add_days(on_date, 10)}
		return get_preview_quotation(
			[{"item_code": item_code, "qty": 1}], user=frappe.session.user, fields=dates
		)

	def test_a_cart_from_before_a_sale_ended_pays_the_price_of_today(self):
		item_code = self.get_item_code(self.make_priced_variant("SALEENDED", default_rate=120))
		self.make_price(
			item_code,
			self.sale_price_list,
			89,
			valid_from=add_days(today(), -30),
			valid_upto=add_days(today(), -1),
		)
		self.sign_in_shopper()

		quotation = self.preview(item_code, add_days(today(), -3))

		self.assertEqual(quotation.items[0].rate, 120)
		self.assertEqual(getdate(quotation.transaction_date), getdate(today()))
		self.assertEqual(getdate(quotation.valid_till), getdate(add_days(today(), 10)))

	def test_a_cart_from_before_a_sale_started_pays_the_sale_price(self):
		item_code = self.get_item_code(self.make_priced_variant("SALESTARTED", default_rate=120))
		self.make_price(item_code, self.sale_price_list, 80, valid_from=today())
		self.sign_in_shopper()

		self.assertEqual(self.preview(item_code, add_days(today(), -1)).items[0].rate, 80)


class TestPriceEditors(PublicPriceTestCase):
	def test_saving_a_size_price_updates_a_future_row_instead_of_adding_one(self):
		route = self.make_priced_variant("FUTUREROW", default_rate=100)
		item_code = self.get_item_code(route)
		self.make_price(item_code, self.sale_price_list, 70, valid_from=add_days(today(), 1))
		variant = frappe.get_doc("Style Attribute Variant", {"route": route})

		variant.save_size_prices([{"item_code": item_code, "sale_rate": 60}])

		self.assertEqual(self.get_sale_rates(item_code), [60])

	def test_bulk_pricing_updates_an_expired_row_instead_of_adding_one(self):
		route = self.make_priced_variant("EXPIREDROW", default_rate=100, sale_rate=70)
		item_code = self.get_item_code(route)
		self.expire(item_code, self.sale_price_list)
		variant = frappe.get_doc("Style Attribute Variant", {"route": route})

		set_variant_prices(
			item_code, sale_rate=60, overwrite_existing=1, style_attribute_variant_list=[variant.name]
		)

		self.assertEqual(self.get_sale_rates(item_code), [60])

	def get_sale_rates(self, item_code):
		filters = {"item_code": item_code, "price_list": self.sale_price_list}
		return frappe.get_all("Item Price", filters=filters, pluck="price_list_rate")


class TestSummerCardWithoutPrice(PublicPriceTestCase):
	def render_card_price(self, amount):
		source = Path(frappe.get_app_path("commera", SUMMER_CARD)).read_text()
		money = CartCurrency.of({"currency": self.store_currency})
		html = frappe.render_template(
			source + "{{ card_price(amount) }}", {"amount": amount, "get_cart_currency": lambda: money}
		)
		return html.rsplit("</div>", 1)[-1].strip()

	def test_a_card_the_market_cannot_price_says_unavailable(self):
		self.assertEqual(self.render_card_price(None), "Unavailable")
		self.assertIn("0.00", self.render_card_price(0))


def get_supplier():
	if supplier := frappe.db.get_value("Supplier", {"disabled": 0}, "name"):
		return supplier
	doc = {"doctype": "Supplier", "supplier_name": f"ZZ Prices {frappe.generate_hash(length=6)}"}
	return frappe.get_doc(doc).insert(ignore_permissions=True).name


def get_uom(name):
	if not frappe.db.exists("UOM", name):
		frappe.get_doc({"doctype": "UOM", "uom_name": name}).insert(ignore_permissions=True)
	return name
