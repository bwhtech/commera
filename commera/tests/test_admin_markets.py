from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import markets as api
from commera.localization.markets import PRIMARY_MARKET
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_market_prices import get_other_currency, make_price_list
from commera.tests.test_markets import UAE, get_store_sale_price_list, make_market, use_markets

OMAN = "Oman"
UNITED_STATES = "United States"


def create(name="Gulf", countries=(UAE,), languages=("ar", "en"), default="ar", **values):
	return api.create_market(
		market_name=name,
		countries=list(countries),
		languages=list(languages),
		default_language=default,
		sale_price_list=values.pop("sale_price_list", get_store_sale_price_list()),
		**values,
	)


def make_user(role=None):
	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": f"market-settings-{frappe.generate_hash(length=10)}@example.com",
				"first_name": "Market settings test",
				"user_type": "System User" if role else "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": role}] if role else [],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class MarketSettingsTestCase(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar", "pt-BR"), unpublished=("fr",))
		use_markets(self)

	def refusal(self, action, *args, **kwargs) -> tuple[str | None, str]:
		"""Read the same structured validation response as the dashboard."""
		frappe.clear_messages()
		response = action(*args, **kwargs)
		return response["field"], response["message"]


class TestAdminMarkets(MarketSettingsTestCase):
	def test_the_primary_market_comes_first_with_the_store_languages_and_prices(self):
		create()

		primary, gulf = api.get_markets()

		self.assertEqual(primary["handle"], PRIMARY_MARKET)
		self.assertTrue(primary["is_primary"])
		self.assertEqual(primary["default_language"], "en")
		self.assertEqual(primary["languages"], ["en", "ar", "pt-BR"])
		self.assertEqual(
			primary["sale_price_list"], frappe.db.get_single_value("Commera Settings", "sale_price_list")
		)
		self.assertEqual(gulf["handle"], "gulf")
		self.assertEqual(gulf["countries"], [UAE])
		self.assertEqual(gulf["languages"], ["ar", "en"])

	def test_the_primary_market_is_read_only(self):
		for action, arguments in (
			(api.update_market, {"handle": PRIMARY_MARKET, "market_name": "Home"}),
			(api.delete_market, {"handle": PRIMARY_MARKET}),
		):
			with self.subTest(action=action.__name__):
				with self.assertRaisesRegex(frappe.ValidationError, "primary market is your store"):
					action(**arguments)

	def test_creating_a_market_makes_its_handle_from_the_name(self):
		market = create("Gulf States", handle="")

		self.assertEqual(market["handle"], "gulf-states")
		self.assertEqual(market["enabled"], 1)
		self.assertEqual(
			market["currency"], frappe.db.get_value("Price List", market["sale_price_list"], "currency")
		)

	def test_new_is_a_valid_market_handle(self):
		market = create("New")
		self.assertEqual(market["handle"], "new")
		self.assertEqual(api.update_market("new", market_name="New market")["handle"], "new")

	def test_an_update_writes_only_the_fields_sent(self):
		market = create(countries=(UAE,))

		saved = api.update_market(market["handle"], countries=[UAE, OMAN])
		self.assertEqual(saved["countries"], [UAE, OMAN])
		self.assertEqual(saved["languages"], ["ar", "en"])

		saved = api.update_market(market["handle"], enabled=0)
		self.assertEqual(saved["enabled"], 0)
		self.assertEqual(saved["countries"], [UAE, OMAN])

		saved = api.update_market(market["handle"], market_name="Gulf States")
		self.assertEqual(saved["handle"], market["handle"])
		self.assertEqual(saved["market_name"], "Gulf States")

	def test_dropping_the_default_language_hands_the_default_to_the_next(self):
		market = create(languages=("ar", "en"), default="ar")

		saved = api.update_market(market["handle"], languages=["en"])

		self.assertEqual(saved["default_language"], "en")
		self.assertEqual(saved["languages"], ["en"])
		field, message = self.refusal(api.update_market, market["handle"], languages=[])
		self.assertEqual((field, message), ("languages", "Choose at least one language."))

	def test_deleting_a_market(self):
		market = create()

		api.delete_market(market["handle"])

		self.assertFalse(frappe.db.exists("Commera Market", market["handle"]))

	def test_the_choices_list_languages_and_selling_price_lists(self):
		choices = api.get_market_choices()

		self.assertEqual(
			[(row["code"], row["published"]) for row in choices["languages"]],
			[("en", True), ("ar", True), ("pt-BR", True), ("fr", False)],
		)
		self.assertIn({"name": UAE, "code": "ae"}, choices["countries"])
		price_lists = {row["name"]: row["currency"] for row in choices["price_lists"]}
		self.assertIn(get_store_sale_price_list(), price_lists)
		self.assertTrue(all(frappe.db.get_value("Price List", name, "selling") for name in price_lists))


class TestMarketValidationMessages(MarketSettingsTestCase):
	def test_each_refusal_names_its_field(self):
		other_currency = make_price_list("Gulf Sale", get_other_currency())
		buying = make_price_list("Gulf Buying", get_other_currency(), selling=0)
		use_storefront_languages(self, "en", published=("en", "ar", "pt-BR", "en-US"), unpublished=("fr",))
		make_market("Oman", [OMAN], "ar")

		for case, arguments, expected_field, expected_message in (
			("no countries", {"countries": ()}, "countries", "Add at least one country"),
			("country taken", {"countries": (OMAN,)}, "countries", "already in market"),
			("unpublished", {"languages": ("fr",), "default": "fr"}, "languages", "not published"),
			("regional", {"languages": ("ar", "pt-BR")}, "languages", "names a region"),
			("price list", {"sale_price_list": buying}, "sale_price_list", "not a selling price list"),
			(
				"compare list",
				{"compare_at_price_list": buying},
				"compare_at_price_list",
				"not a selling price list",
			),
			(
				"currency",
				{"compare_at_price_list": other_currency},
				"compare_at_price_list",
				"Use one currency",
			),
			(
				"url",
				{"countries": (UNITED_STATES,), "languages": ("en",), "default": "en"},
				"urls",
				"/en-us/",
			),
			("handle", {"handle": "Primary"}, "handle", "lowercase letters"),
		):
			with self.subTest(case):
				field, message = self.refusal(create, **arguments)
				self.assertEqual(field, expected_field)
				self.assertIn(expected_message, message)

	def test_an_update_refusal_keeps_the_saved_market(self):
		make_market("Oman", [OMAN], "ar")
		market = create(countries=(UAE,))

		field, _message = self.refusal(api.update_market, market["handle"], countries=[UAE, OMAN])

		self.assertEqual(field, "countries")
		saved = next(row for row in api.get_markets() if row["handle"] == market["handle"])
		self.assertEqual(saved["countries"], [UAE])


class TestMarketTaxTemplate(MarketSettingsTestCase):
	def test_tax_templates_are_offered_only_when_markets_have_the_field(self):
		with patch.object(api, "has_tax_template", return_value=False):
			self.assertIsNone(api.get_market_choices()["tax_templates"])
		with patch.object(api, "has_tax_template", return_value=True):
			self.assertEqual(api.get_market_choices()["tax_templates"], api.get_tax_templates())

	def test_a_tax_template_is_ignored_before_markets_have_the_field(self):
		if api.has_tax_template():
			self.skipTest("Commera Market has a tax template field")

		market = create(tax_template="Any Template")

		self.assertIsNone(market["tax_template"])

	def test_a_tax_template_of_the_store_company_is_saved(self):
		if not api.has_tax_template():
			self.skipTest("Commera Market has no tax template field")
		template = (
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": f"Gulf VAT {frappe.generate_hash(length=6)}",
					"company": api.get_store_company(),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

		market = create(tax_template=template)

		self.assertIn(template, api.get_market_choices()["tax_templates"])
		self.assertEqual(market["tax_template"], template)
		self.assertIsNone(api.update_market(market["handle"], tax_template="")["tax_template"])


class TestMarketSettingsRoles(MarketSettingsTestCase):
	def test_a_commera_admin_without_system_manager_can_manage_markets(self):
		with self.set_user(make_user("Commera Admin")):
			self.assertNotIn("System Manager", frappe.get_roles())
			market = create()
			self.assertEqual([row["handle"] for row in api.get_markets()], [PRIMARY_MARKET, "gulf"])
			self.assertIsNotNone(api.get_market_choices()["countries"])
			self.assertEqual(api.update_market(market["handle"], enabled=0)["enabled"], 0)
			api.delete_market(market["handle"])

		self.assertFalse(frappe.db.exists("Commera Market", market["handle"]))

	def test_a_logged_in_customer_cannot_read_or_write_markets(self):
		market = create()

		with self.set_user(make_user()):
			for action, arguments in (
				(api.get_markets, {}),
				(api.get_market_choices, {}),
				(create, {"name": "Oman", "countries": (OMAN,)}),
				(api.update_market, {"handle": market["handle"], "enabled": 0}),
				(api.delete_market, {"handle": market["handle"]}),
			):
				with self.subTest(action=action.__name__), self.assertRaises(frappe.PermissionError):
					action(**arguments)
