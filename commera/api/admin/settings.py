# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.contacts.doctype.address.address import get_address_display, get_default_address
from frappe.integrations.utils import make_get_request
from frappe.utils.data import cint, cstr, flt, getdate

from commera.install_analytics_demo_data import LEGACY_SESSION_PREFIX, SESSION_PREFIX
from commera.utils import (
	PICKUP_ADDRESS_FIELDS,
	format_addresses,
	get_address_lines,
	get_pickup_addresses,
)

SETTINGS_DOCTYPE = "Commera Settings"
BRANDING_DOCTYPE = "Website Settings"

# Payload keys are the pre-move names on purpose: the Vue tab and the sidebar bind to them.
BRANDING_FIELDS = {
	"brand_logo": "banner_image",
	"footer_logo": "footer_logo",
	"favicon": "favicon",
}

STORE_DETAIL_FIELDS = (
	"store_name",
	"brand_logo",
	"footer_logo",
	"favicon",
	"contact_email",
	"contact_phone",
	"working_hours",
	"company",
)

STORE_DETAIL_SETTINGS_FIELDS = tuple(
	fieldname for fieldname in STORE_DETAIL_FIELDS if fieldname not in BRANDING_FIELDS
)

SHIPPING_FIELDS = ("shipping_rule", "return_period")

PAYMENT_FIELDS = (
	"cod_enabled",
	"cod_charge",
	"cod_charge_applicable_below",
	"charge_account_head",
)

CHECKOUT_FIELDS = ("allow_guest_checkout", "guest_order_link_days")

EMAIL_TEMPLATE_FIELDS = (
	"order_confirmation_email_template",
	"order_cancellation_email_template",
	"item_in_stock_email_template",
)

FOOTER_FIELDS = (
	"facebook_url",
	"twitter_url",
	"instagram_url",
	"snapchat_url",
	"tiktok_url",
	"newsletter_title",
	"newsletter_description",
	"copyright_text",
	"payment_methods_image",
	"vat_certificate_image",
)

# The dashboard's settings tabs that only read and write their own fields; each tuple is also
# the allowlist that stops a save from writing any other field.
SETTINGS_TAB_FIELDS = {
	"payments": PAYMENT_FIELDS,
	"checkout": CHECKOUT_FIELDS,
	"emails": EMAIL_TEMPLATE_FIELDS,
}

# Fields the curated tabs own, so the Advanced tab does not render a second copy.
CURATED_FIELDS = frozenset(
	STORE_DETAIL_FIELDS + SHIPPING_FIELDS + FOOTER_FIELDS + sum(SETTINGS_TAB_FIELDS.values(), ())
)

# Fieldtypes the generic renderer cannot express as one input. Color is skipped for a different
# reason: colour is moving to the theme, though format_theme_css() still reads these fields.
ADVANCED_SKIPPED_FIELDTYPES = frozenset(
	{"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Color"}
)

# The pickup address form lives on the settings screen but picks its country from the Address doctype.
PICKUP_LINK_DOCTYPES = frozenset({"Country"})

GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
GEOCODING_MATCH_LIMIT = 5

NUMERIC_FIELDTYPES = frozenset({"Currency", "Float", "Percent"})
INTEGER_FIELDTYPES = frozenset({"Int", "Check"})


def read_settings_fields(fieldnames):
	"""Read a fixed set of Commera Settings fields for a settings tab."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	return {fieldname: settings.get(fieldname) for fieldname in fieldnames}


def coerce_field_value(fieldtype, value):
	"""Cast an incoming form value to what the docfield expects."""
	if value is None:
		return None
	if fieldtype in INTEGER_FIELDTYPES:
		return cint(value)
	if fieldtype in NUMERIC_FIELDTYPES:
		return flt(value)
	return cstr(value)


def write_settings_fields(allowed_fieldnames, values):
	"""Write only the whitelisted fields, casting each by its docfield type."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="write", throw=True)

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	for fieldname in allowed_fieldnames:
		if fieldname not in values:
			continue
		docfield = meta.get_field(fieldname)
		if not docfield:
			frappe.throw(frappe._("Unknown setting {0}").format(fieldname))
		settings.set(fieldname, coerce_field_value(docfield.fieldtype, values[fieldname]))

	settings.save()
	return {fieldname: settings.get(fieldname) for fieldname in allowed_fieldnames}


def read_branding_fields():
	"""The three brand assets, off Website Settings, under the payload's own key names."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	website_settings = frappe.get_cached_doc(BRANDING_DOCTYPE)
	return {key: website_settings.get(fieldname) for key, fieldname in BRANDING_FIELDS.items()}


def write_branding_fields(values):
	"""Write whichever brand assets the payload carries."""
	if not any(key in values for key in BRANDING_FIELDS):
		return read_branding_fields()

	frappe.has_permission(SETTINGS_DOCTYPE, ptype="write", throw=True)

	meta = frappe.get_meta(BRANDING_DOCTYPE)
	website_settings = frappe.get_doc(BRANDING_DOCTYPE)
	for key, fieldname in BRANDING_FIELDS.items():
		if key in values:
			fieldtype = meta.get_field(fieldname).fieldtype
			website_settings.set(fieldname, coerce_field_value(fieldtype, values[key]))

	# Website Settings is Website Manager's doctype; the store owner never holds that role, so the
	# brand assets are authorised by Commera Settings above and Website Settings is only storage.
	website_settings.save(ignore_permissions=True)
	return {key: website_settings.get(fieldname) for key, fieldname in BRANDING_FIELDS.items()}


def validate_store_details(values):
	"""Guard store_name: commera.seo falls back to the literal "Store", silently rebranding every <title>."""
	if "store_name" in values and not cstr(values["store_name"]).strip():
		frappe.throw(frappe._("Store Name is required"), frappe.MandatoryError)


@frappe.whitelist()
def get_store_settings():
	"""Branding and contact details - the fields a store owner touches most."""
	return read_settings_fields(STORE_DETAIL_SETTINGS_FIELDS) | read_branding_fields()


@frappe.whitelist(methods=["POST"])
def save_store_settings(**kwargs):
	validate_store_details(kwargs)
	return write_settings_fields(STORE_DETAIL_SETTINGS_FIELDS, kwargs) | write_branding_fields(kwargs)


def get_tab_fields(tab: str) -> tuple[str, ...]:
	if tab not in SETTINGS_TAB_FIELDS:
		frappe.throw(frappe._("Unknown settings tab {0}").format(tab))
	return SETTINGS_TAB_FIELDS[tab]


@frappe.whitelist()
def get_tab_settings(tab: str):
	return read_settings_fields(get_tab_fields(tab))


@frappe.whitelist(methods=["POST"])
def save_tab_settings(tab: str, **kwargs):
	return write_settings_fields(get_tab_fields(tab), kwargs)


def get_advanced_docfields():
	"""Every editable docfield the four curated tabs do not already cover, in layout order."""
	docfields = []
	for docfield in frappe.get_meta(SETTINGS_DOCTYPE).fields:
		if docfield.fieldtype in ADVANCED_SKIPPED_FIELDTYPES:
			continue
		if docfield.fieldname in CURATED_FIELDS:
			continue
		if docfield.hidden or docfield.read_only:
			continue
		docfields.append(docfield)

	return docfields


@frappe.whitelist()
def get_advanced_settings():
	"""The long tail of setup fields, grouped by the section they sit under in Desk."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	advanced_fieldnames = {docfield.fieldname for docfield in get_advanced_docfields()}

	groups = []
	group_by_label = {}
	child_tables = []
	current_group_label = "General"

	for docfield in frappe.get_meta(SETTINGS_DOCTYPE).fields:
		if docfield.fieldtype in ("Tab Break", "Section Break"):
			if docfield.label:
				current_group_label = docfield.label
			continue

		if docfield.fieldtype == "Table":
			if docfield.fieldname not in CURATED_FIELDS:
				child_tables.append({"label": docfield.label, "options": docfield.options})
			continue

		if docfield.fieldname not in advanced_fieldnames:
			continue

		group = group_by_label.get(current_group_label)
		if group is None:
			group = {"label": current_group_label, "fields": []}
			group_by_label[current_group_label] = group
			groups.append(group)

		group["fields"].append(
			{
				"fieldname": docfield.fieldname,
				"label": docfield.label,
				"fieldtype": docfield.fieldtype,
				"options": docfield.options,
				"description": docfield.description,
				"value": settings.get(docfield.fieldname),
			}
		)

	# The flag rides this answer rather than costing the tab its own round trip: the panel
	# already re-reads on activation, so it cannot go stale while the tab is open.
	return {
		"groups": groups,
		"child_tables": child_tables,
		"can_install_demo_data": not has_real_orders(),
	}


@frappe.whitelist(methods=["POST"])
def save_advanced_settings(**kwargs):
	advanced_fieldnames = [docfield.fieldname for docfield in get_advanced_docfields()]
	unknown = set(kwargs) - set(advanced_fieldnames)
	if unknown:
		frappe.throw(frappe._("Not an advanced setting: {0}").format(", ".join(sorted(unknown))))

	return write_settings_fields(advanced_fieldnames, kwargs)


def has_real_orders() -> bool:
	"""Counting the seeded orders off the total, rather than filtering them out: an order whose
	session id is NULL belongs on the real side, and `not like` would drop it."""
	total_orders = frappe.db.count("Sales Order")
	if not total_orders:
		return False

	seeded_orders = frappe.db.count(
		"Sales Order", {"custom_analytics_session_id": ("like", f"{SESSION_PREFIX}%")}
	) + frappe.db.count("Sales Order", {"custom_analytics_session_id": ("like", f"{LEGACY_SESSION_PREFIX}%")})
	return total_orders > seeded_orders


@frappe.whitelist(methods=["POST"])
def install_demo_data():
	"""Seed the demo storefront. Delegates to the controller so the Desk button and this screen
	queue the same job; System Manager only, because the seeder overwrites live store config."""
	frappe.only_for("System Manager")
	if has_real_orders():
		frappe.throw(frappe._("This store has its own orders. Demo data would overwrite its setup."))

	return frappe.get_doc(SETTINGS_DOCTYPE).install_demo_data()


def get_linked_doctypes():
	"""Doctypes reachable through a Commera Settings Link field."""
	return {
		docfield.options
		for docfield in frappe.get_meta(SETTINGS_DOCTYPE).fields
		if docfield.fieldtype == "Link" and docfield.options
	}


@frappe.whitelist()
def get_link_options(doctype: str, search_text: str | None = None):
	"""Options for a Link control on the settings screen."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	if doctype not in get_linked_doctypes() | PICKUP_LINK_DOCTYPES:
		frappe.throw(frappe._("{0} is not linked from {1}").format(doctype, SETTINGS_DOCTYPE))

	filters = {}
	if search_text:
		filters["name"] = ("like", f"%{cstr(search_text)}%")

	# ponytail: first 100 matches only - the picker searches server-side, so anything further
	# down is reachable by typing; paginate if a doctype outgrows even a searched list
	records = frappe.get_all(doctype, filters=filters, pluck="name", order_by="name asc", limit=100)
	return [{"label": name, "value": name} for name in records]


def read_company_address(company: str) -> str | None:
	"""The company's default address as plain text. get_address_display renders the address template,
	which is HTML, so it goes through the dashboard's own <br>-to-newline pass."""
	address = get_default_address("Company", company)
	return get_address_lines(get_address_display(address)) if address else None


def read_fiscal_year(company: str) -> str | None:
	"""The fiscal year today falls in. A site can be missing one entirely, hence raise_on_missing."""
	from erpnext.accounts.utils import get_fiscal_year

	fiscal_year = get_fiscal_year(getdate(), company=company, raise_on_missing=False)
	return fiscal_year[0] if fiscal_year else None


@frappe.whitelist()
def get_company_profile():
	"""The store's real accounting identity, read-only — edited in Desk, never here. None on a
	half-configured site so the settings dialog still opens."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	company = frappe.get_cached_value(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, "company")
	if not company:
		return None

	details = frappe.get_cached_value(
		"Company", company, ["name", "abbr", "default_currency", "country", "tax_id"], as_dict=True
	)
	if not details:
		return None

	return {
		"name": details.name,
		"abbr": details.abbr,
		"currency": details.default_currency,
		"country": details.country,
		"tax_id": details.tax_id,
		"fiscal_year": read_fiscal_year(company),
		"address": read_company_address(company),
	}


@frappe.whitelist()
def get_locations():
	"""Every active warehouse, and whether shoppers can collect an order from it."""
	settings = read_settings_fields(("ecommerce_warehouse", "store_pickup_enabled"))

	warehouses = frappe.get_list(
		"Warehouse",
		filters={"disabled": 0, "is_group": 0},
		fields=["name", "warehouse_name", "company", "custom_store_pickup"],
		order_by="warehouse_name asc",
	)
	pickup_addresses = get_pickup_addresses([warehouse.name for warehouse in warehouses])
	company_countries = dict(
		frappe.get_all(
			"Company",
			filters={"name": ["in", list({warehouse.company for warehouse in warehouses})]},
			fields=["name", "country"],
			as_list=True,
		)
	)

	return {
		"store_pickup_enabled": cint(settings["store_pickup_enabled"]),
		"warehouses": [
			{
				"name": warehouse.name,
				"warehouse_name": warehouse.warehouse_name,
				"company": warehouse.company,
				# What a new pickup address starts with, since almost every shop is in its company's country.
				"country": company_countries.get(warehouse.company) or "",
				"is_ecommerce_warehouse": warehouse.name == settings["ecommerce_warehouse"],
				"allow_pickup": cint(warehouse.custom_store_pickup),
				"address": format_pickup_address(pickup_addresses.get(warehouse.name)),
			}
			for warehouse in warehouses
		],
	}


def format_pickup_address(address) -> dict | None:
	if not address:
		return None

	return {
		**{fieldname: address.get(fieldname) or "" for fieldname in PICKUP_ADDRESS_FIELDS},
		"name": address.name,
		"display": format_addresses([address], address_type="Shop")[0]["display"],
	}


@frappe.whitelist(methods=["POST"])
def save_store_pickup(enabled: int):
	write_settings_fields(("store_pickup_enabled",), {"store_pickup_enabled": enabled})
	return get_locations()


@frappe.whitelist(methods=["POST"])
def save_warehouse_pickup(warehouse: str, allow_pickup: int):
	warehouse_doc = frappe.get_doc("Warehouse", warehouse)
	warehouse_doc.custom_store_pickup = cint(allow_pickup)
	warehouse_doc.save()
	return get_locations()


@frappe.whitelist(methods=["POST"])
def save_pickup_address(warehouse: str, values: dict | str):
	"""Create or update the one Shop address checkout sends shoppers to for this warehouse."""
	values = frappe.parse_json(values)
	warehouse_doc = frappe.get_doc("Warehouse", warehouse)
	warehouse_doc.check_permission("write")

	existing = get_pickup_addresses([warehouse]).get(warehouse)
	if existing:
		address = frappe.get_doc("Address", existing.name)
	else:
		address = frappe.new_doc("Address")
		address.address_type = "Shop"
		address.append("links", {"link_doctype": "Warehouse", "link_name": warehouse})

	for fieldname in PICKUP_ADDRESS_FIELDS:
		value = values.get(fieldname)
		# The pin arrives as GeoJSON; cstr would store a parsed one as a Python repr Desk cannot draw.
		address.set(fieldname, frappe.as_json(value) if isinstance(value, dict) else cstr(value).strip())
	address.address_title = address.address_title or warehouse_doc.warehouse_name
	address.save()
	return get_locations()


@frappe.whitelist()
def find_address_location(query: str):
	"""Where OpenStreetMap places an address, best match first, so the pin starts at the shop instead of
	mid-ocean and the owner can pick another match when the first is wrong."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)

	query = cstr(query).strip()
	if not query:
		return []

	try:
		results = make_get_request(
			GEOCODING_URL,
			params={"q": query, "format": "json", "limit": GEOCODING_MATCH_LIMIT},
			headers={"User-Agent": f"Commera ({frappe.local.site})"},
		)
	# make_request has already logged whatever went wrong; a failed lookup only means placing the pin by hand.
	except Exception:
		return []

	if not isinstance(results, list):
		return []
	return [format_geocoding_match(result) for result in results if result.get("lat") and result.get("lon")]


def format_geocoding_match(result: dict) -> dict:
	bounding_box = result.get("boundingbox") or []
	bounds = None
	# Nominatim orders the box south, north, west, east; Leaflet wants [[south, west], [north, east]].
	if len(bounding_box) == 4:
		south, north, west, east = (flt(value) for value in bounding_box)
		bounds = [[south, west], [north, east]]

	return {
		"label": cstr(result.get("display_name")),
		"latitude": flt(result.get("lat")),
		"longitude": flt(result.get("lon")),
		"bounds": bounds,
	}


PROFILE_FIELDS = ("first_name", "last_name", "user_image")


@frappe.whitelist()
def get_profile():
	"""The signed-in user's own profile. Always self-scoped - this is not user administration."""
	user = frappe.get_cached_doc("User", frappe.session.user)
	return {
		"name": user.name,
		"email": user.email,
		"full_name": user.full_name,
		"first_name": user.first_name,
		"last_name": user.last_name,
		"user_image": user.user_image,
	}


@frappe.whitelist(methods=["POST"])
def save_profile(**kwargs):
	"""Edit your own profile only; changing anyone else's is User administration's job."""
	user = frappe.get_doc("User", frappe.session.user)
	for field in PROFILE_FIELDS:
		if field in kwargs:
			user.set(field, kwargs[field])
	user.save(ignore_permissions=True)

	return get_profile()
