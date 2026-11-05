import frappe
from frappe.utils.data import getdate
from frappe.utils.nestedset import get_root_of

from commera.onboarding import run_frappe_setup, seed_commera_settings

TEST_COMPANY = "Lifestyle Demo"
TEST_ABBR = "LSD"
TEST_CURRENCY = "INR"
TEST_ITEM_GROUP = "Interior Accessories"
SALE_PRICE_LIST = "Sale Price List"


def before_tests():
	"""Seed the ERPNext setup a bare CI site never gets, so the suite has a company to bill against."""
	complete_setup_wizard()
	seed_erpnext_test_defaults()
	seed_storefront_item_group()
	seed_test_commera_settings()

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- persist seed data before the test run begins


def complete_setup_wizard():
	# Frappe seeds via the wizard only on a single-app site, so our four-app CI site gets none. The
	# fiscal-year dates are explicit: without them Fiscal Year validation aborts Company creation.
	if frappe.is_setup_complete():
		return

	today = getdate()
	run_frappe_setup(
		{
			"language": "English",
			"email": "test@lifestyle.local",
			"full_name": "Test User",
			"password": "test",
			"country": "India",
			"timezone": "Asia/Kolkata",
			"currency": TEST_CURRENCY,
			"company_name": TEST_COMPANY,
			"company_abbr": TEST_ABBR,
			"chart_of_accounts": "Standard",
			"fy_start_date": today.replace(month=1, day=1).isoformat(),
			"fy_end_date": today.replace(month=12, day=31).isoformat(),
		}
	)


def seed_erpnext_test_defaults():
	if "erpnext" not in frappe.get_installed_apps():
		return

	from erpnext.setup.utils import enable_all_roles_and_domains, set_defaults_for_tests

	enable_all_roles_and_domains()
	set_defaults_for_tests()

	# set_defaults_for_tests() points both defaults at the tree roots, which are group nodes — every
	# Customer the suite inserts without naming a group would be refused by validate_customer_group().
	for doctype in ("Customer Group", "Territory"):
		leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft")
		if leaf:
			key = frappe.scrub(doctype)
			frappe.db.set_single_value("Selling Settings", key, leaf)
			frappe.db.set_default(key, leaf)


def seed_storefront_item_group():
	# commera makes `custom_displayname` mandatory on Item Group, so the wizard's own stock groups
	# never insert and the site is left with nothing but the root.
	if frappe.db.exists("Item Group", TEST_ITEM_GROUP):
		return

	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": TEST_ITEM_GROUP,
			"custom_displayname": TEST_ITEM_GROUP,
			"parent_item_group": get_root_of("Item Group"),
			"is_group": 0,
		}
	).insert(ignore_permissions=True)


def seed_test_commera_settings():
	seed_commera_settings(TEST_COMPANY)
	# Not mandatory, but the cart and search suites read it straight off this Single to build fixtures.
	frappe.db.set_single_value("Commera Settings", "sale_price_list", seed_sale_price_list())
	# Storefront suites render as Guest, and a new store starts private.
	frappe.db.set_single_value("Commera Settings", "storefront_published", 1)


def seed_sale_price_list() -> str:
	"""A second selling list, so a discounted fixture can undercut the default one."""
	if not frappe.db.exists("Price List", SALE_PRICE_LIST):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": SALE_PRICE_LIST,
				"selling": 1,
				"currency": TEST_CURRENCY,
			}
		).insert(ignore_permissions=True)

	return SALE_PRICE_LIST
