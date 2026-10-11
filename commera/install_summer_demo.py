"""One-shot seeder for a Summer storefront demo site, in whatever currency it is handed.
create_price_lists is skipped: it hardcodes USD, which blocks Sales Invoices on a non-USD company."""

import frappe
from frappe.permissions import add_permission, update_permission_property
from frappe.utils.data import flt

from commera.install_analytics_demo_data import install_analytics_demo_data
from commera.install_demo_data import (
	configure_commera_settings,
	create_item_attributes,
	ensure_warehouse_exists,
)
from commera.install_fashion_demo_data import (
	DEFAULT_SIZES,
	FASHION_PRODUCTS,
	install_fashion_demo_data,
)
from commera.install_summer_theme_data import HERO_SLIDES, PRODUCTS_URL, install_summer_theme_data
from commera.migrate import activate_summer_theme

DEMO_SIZES = DEFAULT_SIZES
SALE_PRICE_LIST = "Sale Price List"
SHIPPING_RULE = "Standard Shipping"
COD_CHARGE_ACCOUNT = "Cash on Delivery Charges"
SHOPPER_ROLE = "Customer"

DEFAULT_CURRENCY = "SAR"

# FASHION_PRODUCTS carries dollar-scale numbers, so price_multiplier restates them in the site's own
# currency. Rates are recomputed from it on every run - scaling in place would compound on a re-run.
CURRENCY_PROFILES = {
	"SAR": {
		"country": "Saudi Arabia",
		"symbol": "ر.س",
		"price_multiplier": 3.75,
		"price_rounding": 10,
		"free_shipping_above": 299,
		"flat_shipping_charge": 25,
		"cod_charge": 15,
		"cod_charge_applicable_below": 299,
		"contact_phone": "+966 55 123 4567",
	},
	"INR": {
		"country": "India",
		"symbol": "₹",
		"price_multiplier": 50,
		"price_rounding": 100,
		"free_shipping_above": 999,
		"flat_shipping_charge": 99,
		"cod_charge": 49,
		"cod_charge_applicable_below": 999,
		"contact_phone": "+91 98765 43210",
	},
}

DEFAULT_HOMEPAGE_IMAGES = "/assets/commera/images/homepage/demo"
DEFAULT_HERO_BANNERS = ("hero-1.webp", "hero-2.webp", "hero-3.webp", "hero-4.webp")
DEFAULT_PROMO_TILES = ("tile-1.webp", "tile-2.webp", "tile-3.webp", "tile-4.webp")
DEFAULT_WIDE_BANNER = "wide-1.webp"

STORE_COPY = {
	"store_name": "Summer",
	"contact_email": "hello@summer.demo",
	"working_hours": "Mon - Sat, 10:00 - 19:00",
	"newsletter_title": "Sign Up For Newsletter",
	"newsletter_description": "Get the latest drops and offers straight to your inbox.",
	# The template already renders "© {year}" ahead of this, so the symbol and year stay out of it.
	"copyright_text": "Summer. All Rights Reserved.",
}

# Every URL must point at a route this storefront actually serves.
FOOTER_SECTIONS = (
	{
		"section_title": "Our Stores",
		"links": (
			"New York",
			"London SF",
			"Edinburgh",
			"Los Angeles",
			"Chicago",
			"Las Vegas",
		),
	},
	{
		"section_title": "Useful Links",
		"links": (
			("Privacy Policy", "/en/products"),
			("Returns", "/en/account/orders"),
			("Terms & Conditions", "/en/products"),
			("Contact Us", "/en/account/profile"),
			("Latest News", "/en/products"),
			("Our Sitemap", "/sitemap.xml"),
		),
	},
	{
		"section_title": "Footer Menu",
		"links": (
			("New Collection", "/en/products"),
			("Woman Dress", "/en/products"),
			("Contact Us", "/en/account/profile"),
			("Latest News", "/en/products"),
			("My Account", "/en/account/dashboard"),
		),
	},
)


def install_summer_demo(currency=DEFAULT_CURRENCY):
	"""Seed a demo storefront end to end in `currency`. Safe to re-run."""
	profile = get_currency_profile(currency)

	configure_site_defaults(currency, profile)
	align_store_currency(currency)
	save_sale_price_list(currency)
	create_item_attributes()
	normalise_size_attribute()
	save_shipping_rule(profile)

	configure_commera_settings()
	apply_store_copy(profile)

	activate_summer_theme()
	install_fashion_demo_data()
	apply_catalogue_prices(profile)
	install_summer_theme_data()
	apply_hero_prices(profile)

	save_default_homepage()
	save_footer_sections()
	save_mode_of_payment_accounts()
	allow_shoppers_to_select_accounts()

	seed_storefront_analytics()
	# The catalogue and the analytics orders above were written against whatever currency the price
	# lists carried at insert time, so the store is only consistent once it is swept again.
	align_store_currency(currency)

	# nosemgrep: frappe-manual-commit  # seeder, runs from the console or a long background job
	frappe.db.commit()
	frappe.clear_cache()
	print(f"✅ Summer demo seeded in {currency}")


def get_currency_profile(currency):
	profile = CURRENCY_PROFILES.get(currency)
	if not profile:
		frappe.throw(
			frappe._("No demo currency profile for {0}. Known: {1}.").format(
				currency, ", ".join(sorted(CURRENCY_PROFILES))
			)
		)

	return profile


def seed_storefront_analytics():
	"""Give the analytics screen a store worth looking at."""
	# Must run after the catalogue: the events and orders it writes reference real item codes.
	install_analytics_demo_data()


def configure_site_defaults(currency, profile):
	"""The site-level settings that silently break a paid checkout later."""
	# A blank System Settings.language crashes money_in_words (num2words(lang=None)) on every invoice;
	# a Contact whose email_id is not an address is rejected by the gateways.
	frappe.db.set_single_value("System Settings", "language", "en")
	frappe.db.set_single_value("System Settings", "country", profile["country"])
	frappe.db.set_default("currency", currency)
	# A second, separate currency surface: utils.get_currency_symbol reads Global Defaults, not this default.
	frappe.db.set_single_value("Global Defaults", "default_currency", currency)
	frappe.db.set_single_value("Global Defaults", "country", profile["country"])
	# Frappe ships most currencies disabled, and a disabled one cannot be picked on any document.
	frappe.db.set_value("Currency", currency, "enabled", 1)

	contact = frappe.db.get_value("Contact", {"user": "Administrator"})
	if contact:
		frappe.db.set_value(
			"Contact", contact, "email_id", frappe.db.get_value("User", "Administrator", "email")
		)


def align_store_currency(currency):
	"""Put the company, its accounts and every price its catalogue carries into one currency."""
	# The three-way mismatch this undoes (system INR, company SAR, price list USD) throws
	# "Party Account ... currency and document currency should be same" on every Sales Invoice.
	company = get_company()
	frappe.db.set_value("Company", company, "default_currency", currency)

	# ponytail: written straight to the table because ERPNext refuses a currency change once a
	# company has transactions — safe on a seeded demo, revisit if this is ever run on a live store.
	account = frappe.qb.DocType("Account")
	frappe.qb.update(account).set(account.account_currency, currency).where(
		(account.company == company) & (account.account_currency != currency)
	).run()

	price_list = frappe.qb.DocType("Price List")
	frappe.qb.update(price_list).set(price_list.currency, currency).where(
		price_list.currency != currency
	).run()

	# Item Price copies its currency from the price list at insert time and never re-reads it.
	item_price = frappe.qb.DocType("Item Price")
	frappe.qb.update(item_price).set(item_price.currency, currency).where(
		item_price.currency != currency
	).run()


def save_sale_price_list(currency):
	"""Built here rather than through install_demo_data.create_price_lists, which pins USD."""
	if frappe.db.exists("Price List", SALE_PRICE_LIST):
		frappe.db.set_value("Price List", SALE_PRICE_LIST, "currency", currency)
		return

	frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": SALE_PRICE_LIST,
			"currency": currency,
			"enabled": 1,
			"buying": 0,
			"selling": 1,
		}
	).insert(ignore_permissions=True)


def normalise_size_attribute():
	"""Replace ERPNext's Small/Medium/Large Size values with the demo's literal S/M/L/XL."""
	# ERPNext ships Size as Small/Medium/Large abbreviated S/M/L, so a literal "S" fails as invalid.
	attribute = frappe.get_doc("Item Attribute", "Size")
	existing = {row.attribute_value for row in attribute.item_attribute_values}
	if set(DEMO_SIZES).issubset(existing):
		return

	if frappe.db.exists("Item Variant Attribute", {"attribute": "Size"}):
		frappe.throw(
			frappe._("Size attribute is already used by item variants — reset it by hand before seeding.")
		)

	attribute.item_attribute_values = []
	for size in DEMO_SIZES:
		attribute.append("item_attribute_values", {"attribute_value": size, "abbr": size})

	attribute.save(ignore_permissions=True)


def save_shipping_rule(profile):
	"""Rebuild the rule's brackets every run, so a currency switch rescales the shipping charge too."""
	company = get_company()
	rule = (
		frappe.get_doc("Shipping Rule", SHIPPING_RULE)
		if frappe.db.exists("Shipping Rule", SHIPPING_RULE)
		else frappe.new_doc("Shipping Rule")
	)
	rule.update(
		{
			"label": SHIPPING_RULE,
			"shipping_rule_type": "Selling",
			"calculate_based_on": "Net Total",
			"company": company,
			"account": get_freight_account(),
			"cost_center": frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name"),
		}
	)
	rule.conditions = []
	rule.append(
		"conditions",
		{
			"from_value": 0,
			"to_value": profile["free_shipping_above"],
			"shipping_amount": profile["flat_shipping_charge"],
		},
	)
	rule.append(
		"conditions",
		{"from_value": profile["free_shipping_above"], "to_value": 9999999, "shipping_amount": 0},
	)
	rule.save(ignore_permissions=True)


def apply_store_copy(profile):
	"""Local COD thresholds and the storefront's own name, over what configure_commera_settings left."""
	settings = frappe.get_doc("Commera Settings")
	settings.cod_enabled = 1
	settings.cod_charge = profile["cod_charge"]
	settings.cod_charge_applicable_below = profile["cod_charge_applicable_below"]
	settings.ecommerce_warehouse = ensure_warehouse_exists()
	# Without this, set_cod_charges throws "Set a Charge Account Head in Commera Settings...".
	settings.charge_account_head = ensure_cod_charge_account()

	settings.contact_phone = profile["contact_phone"]
	for fieldname, value in STORE_COPY.items():
		settings.set(fieldname, value)

	settings.save(ignore_permissions=True)


def apply_catalogue_prices(profile):
	"""Restate every catalogue price at the store's own scale, rounded to a plausible retail number."""
	for product in FASHION_PRODUCTS:
		rates = {
			"Standard Selling": to_local_price(product["base_price"], profile),
			SALE_PRICE_LIST: to_local_price(product["sale_price"], profile),
		}
		for price_list, rate in rates.items():
			for name in frappe.get_all(
				"Item Price",
				filters={"item_code": ["like", f"{product['code']}-%"], "price_list": price_list},
				pluck="name",
			):
				frappe.db.set_value("Item Price", name, "price_list_rate", rate)


def to_local_price(amount, profile):
	"""Dollar-scale amount as a local price ending in 9, the shape a shopper expects."""
	step = profile["price_rounding"]
	return round(flt(amount) * profile["price_multiplier"] / step) * step - 1


def apply_hero_prices(profile):
	"""Restate the hero slides' dollar copy at the catalogue's local scale."""
	# Read back from HERO_SLIDES, never from the subheading a previous run wrote: re-parsing that
	# compounds the scaling, and a symbol carrying a "." of its own corrupts the number outright.
	settings = frappe.get_doc("Summer Theme Settings")
	for slide, source in zip(settings.hero_slides, HERO_SLIDES, strict=False):
		amount = source["subheading"].lstrip("$")
		if not amount.replace(".", "").isdigit():
			continue
		slide.subheading = f"{profile['symbol']}{to_local_price(amount, profile):,}"

	settings.save(ignore_permissions=True)


def save_default_homepage():
	"""Fill Landing Page Settings so the un-themed storefront is a real page, not an empty one."""
	settings = frappe.get_doc("Landing Page Settings")

	settings.hero_banner = []
	for banner in DEFAULT_HERO_BANNERS:
		settings.append(
			"hero_banner",
			{"banner_image": f"{DEFAULT_HOMEPAGE_IMAGES}/{banner}", "url": PRODUCTS_URL},
		)

	for index, tile in enumerate(DEFAULT_PROMO_TILES, start=1):
		settings.set(f"gif_{index}", f"{DEFAULT_HOMEPAGE_IMAGES}/{tile}")
		settings.set(f"gif_url_{index}", PRODUCTS_URL)

	settings.banner_1 = f"{DEFAULT_HOMEPAGE_IMAGES}/{DEFAULT_WIDE_BANNER}"
	settings.banner_url_1 = PRODUCTS_URL

	published = frappe.get_all(
		"Style Attribute Variant", filters={"is_published": 1}, pluck="name", order_by="creation"
	)
	settings.new_arrivals = []
	settings.best_picks = []
	for name in published[:6]:
		settings.append("new_arrivals", {"item_variant": name})
	for name in published[6:12]:
		settings.append("best_picks", {"item_variant": name})

	settings.save(ignore_permissions=True)


def save_footer_sections():
	"""Rebuild the footer from the reference columns, replacing whatever the base seeder left."""
	settings = frappe.get_doc("Commera Settings")
	settings.footer_sections = []

	for section_order, section in enumerate(FOOTER_SECTIONS, start=1):
		title = section["section_title"]
		config = (
			frappe.get_doc("Footer Section Config", title)
			if frappe.db.exists("Footer Section Config", title)
			else frappe.new_doc("Footer Section Config")
		)
		config.section_title = title
		config.section_order = section_order
		config.enabled = 1
		config.footer_links = []

		for link_order, link in enumerate(section["links"], start=1):
			label, url = link if isinstance(link, tuple) else (link, "/en/products")
			config.append(
				"footer_links",
				{"link_label": label, "link_url": url, "link_order": link_order, "enabled": 1},
			)

		config.save(ignore_permissions=True)
		settings.append(
			"footer_sections",
			{"footer_section": config.name, "section_order": section_order, "enabled": 1},
		)

	settings.save(ignore_permissions=True)


def save_mode_of_payment_accounts():
	"""Give every Mode of Payment a company account row."""
	# Without one, create_payment_entry throws "Please set default Cash or Bank account in Mode of Payment".
	company = get_company()
	abbr = frappe.db.get_value("Company", company, "abbr")
	accounts = {
		"Cash": frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0})
		or f"Cash - {abbr}",
		"Bank": frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0})
		or f"Bank Account - {abbr}",
	}

	for mode_name in frappe.get_all("Mode of Payment", pluck="name"):
		mode = frappe.get_doc("Mode of Payment", mode_name)
		if any(row.company == company for row in mode.accounts):
			continue

		default_account = accounts.get(mode.type)
		if not default_account or not frappe.db.exists("Account", default_account):
			continue

		mode.append("accounts", {"company": company, "default_account": default_account})
		mode.save(ignore_permissions=True)


def ensure_cod_charge_account():
	"""COD bills to an account of its own, never the shipping rule's."""
	# ERPNext's shipping rule rewrites any tax row carrying the rule's account head, so a COD charge
	# sharing it comes out silently restated as the shipping amount.
	company = get_company()
	abbr = frappe.db.get_value("Company", company, "abbr")
	account_name = f"{COD_CHARGE_ACCOUNT} - {abbr}"
	if frappe.db.exists("Account", account_name):
		return account_name

	freight_account = get_freight_account()
	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": COD_CHARGE_ACCOUNT,
			"company": company,
			"parent_account": frappe.db.get_value("Account", freight_account, "parent_account"),
			"account_type": "Chargeable",
			"root_type": "Expense",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)

	return account_name


def allow_shoppers_to_select_accounts():
	"""A storefront cart cannot be saved by its own shopper without this."""
	# ERPNext v17's get_party_account permission-checks the receivable account while the Quotation is
	# saved under the shopper's session, so a Customer with no Account perm at all fails every cart.
	# ponytail: select-only, granted as demo site data — the product fix (issue #60) belongs in the
	# checkout API, which should write the cart through system_user_session as place_order already does.
	if frappe.db.exists("Custom DocPerm", {"parent": "Account", "role": SHOPPER_ROLE, "permlevel": 0}):
		return

	add_permission("Account", SHOPPER_ROLE, 0)
	update_permission_property("Account", SHOPPER_ROLE, 0, "read", 0)
	update_permission_property("Account", SHOPPER_ROLE, 0, "select", 1)


def get_freight_account():
	company = get_company()
	abbr = frappe.db.get_value("Company", company, "abbr")
	return (
		frappe.db.get_value(
			"Account", {"account_name": "Freight and Forwarding Charges", "company": company}, "name"
		)
		or f"Freight and Forwarding Charges - {abbr}"
	)


def get_company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")


def get_company_currency():
	return frappe.db.get_value("Company", get_company(), "default_currency") or DEFAULT_CURRENCY
