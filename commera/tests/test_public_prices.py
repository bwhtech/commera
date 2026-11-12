"""The storefront prices a product only from the Item Price rows ERPNext would use today, and the cart
lets ERPNext price a line from the compare-at list as it prices one from the sale list."""

from pathlib import Path

import frappe
from frappe.utils import add_days, today

from commera.core import get_party
from commera.localization.cart_currency import CartCurrency
from commera.localization.content import SHOP_WIDE
from commera.localization.market_prices import MarketPrices
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

	def make_party_price(self, item_code, price_list, rate, **party):
		price = {"doctype": "Item Price", "item_code": item_code, "price_list": price_list}
		return frappe.get_doc({**price, "price_list_rate": rate, **party}).insert().name

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
		self.make_party_price(self.get_item_code(route), self.sale_price_list, 17, supplier=get_supplier())

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
		item = frappe.get_doc("Item", item_code)
		item.append("uoms", {"uom": get_uom("ZZ Box"), "conversion_factor": 10})
		item.sales_uom = "ZZ Box"
		item.save()
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
		self.make_party_price(item_code, self.sale_price_list, 250, customer=customer)
		frappe.set_user(shopper)

		line = self.lines(self.add(item_code))[item_code]

		self.assertEqual(line["rate"], 250)


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
