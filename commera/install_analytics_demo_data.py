"""Seeds ~60 days of storefront analytics events plus the orders they attribute to.

Re-runs replace rather than double: "dmoev*" events, "dmo-" sessions, "dmolegacy-" on orders removal unstamps.
"""

import json
import random

import frappe
from frappe import _
from frappe.utils.data import add_days, add_to_date, cint, flt, get_datetime, getdate, now_datetime

from commera.telemetry import data_source

EVENT_NAME_PREFIX = "dmoev"
SESSION_PREFIX = "dmo-"
LEGACY_SESSION_PREFIX = "dmolegacy-"
DEMO_CUSTOMER_PREFIX = "Demo Shopper"
CATALOG_PRICE_LIST = "Standard Selling"
FALLBACK_PRICE = 799.0
RANDOM_SEED = 20260821

HISTORY_DAYS = 60
DEMO_CUSTOMER_COUNT = 300
BASE_SESSIONS_PER_DAY = 175
LOGGED_IN_SHARE = 0.35
RECOVERABLE_QUOTATIONS = 15
# Parked outside every dashboard range preset (7/30/90 days) so they never contaminate its revenue.
PRIOR_HISTORY_FROM_DAY = -180
PRIOR_HISTORY_TO_DAY = -150
PRIOR_HISTORY_ORDERS = 15

# funnel step-through rates for an average session; multiplied by each channel's intent.
VIEW_ITEM_RATE = 0.45
ADD_TO_CART_RATE = 0.31
BEGIN_CHECKOUT_RATE = 0.38
PURCHASE_RATE = 0.30
MAX_STEP_RATE = 0.95
# the store's hero product pulls this many times its share of product views
HERO_VIEW_WEIGHT = 4.5
# last-day sessions stop short of now, so the only traffic inside Live View's window is the live tail
LIVE_TAIL_MARGIN_MINUTES = 60
# a session must not span two days, and the longest visit runs about seven events four minutes apart
LAST_HOUR_OF_DAY = 23
MAX_SESSION_MINUTES = 28
# session growth across the window, so the "vs previous period" deltas come out positive.
GROWTH_OVER_WINDOW = 0.45

# hour-of-day weights, index = hour. Each channel gets the shape its audience actually browses in.
EVENING_HOURS = (1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 6, 7, 6, 6, 7, 9, 12, 18, 24, 26, 22, 14, 6)
MORNING_HOURS = (1, 1, 1, 1, 1, 2, 5, 14, 26, 24, 18, 12, 9, 8, 7, 6, 6, 6, 6, 5, 4, 3, 2, 1)
WORKDAY_HOURS = (1, 1, 1, 1, 1, 2, 3, 6, 11, 15, 16, 15, 13, 14, 15, 16, 16, 15, 14, 13, 11, 8, 5, 2)
GENERAL_HOURS = (1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 11, 11, 11, 11, 11, 12, 15, 19, 24, 26, 23, 17, 10, 4)

CHANNELS = (
	{
		"key": "direct",
		"utm_source": None,
		"utm_medium": None,
		"utm_campaign": None,
		"referrer": None,
		"base_share": 0.30,
		"campaign": None,
		"devices": (("Mobile", 0.50), ("Desktop", 0.42), ("Tablet", 0.08)),
		"hours": GENERAL_HOURS,
		"weekend_lift": 1.1,
		"intent": 0.7,
		"collection": "all",
		"landing": (("/en", 0.72), ("/en/products", 0.28)),
	},
	{
		"key": "google-organic",
		"utm_source": "google",
		# organic carries no campaign — an empty utm_campaign is the correct, realistic behaviour
		"utm_medium": "organic",
		"utm_campaign": None,
		"referrer": "https://www.google.com/",
		"base_share": 0.26,
		"campaign": None,
		"devices": (("Mobile", 0.52), ("Desktop", 0.40), ("Tablet", 0.08)),
		"hours": WORKDAY_HOURS,
		"weekend_lift": 0.95,
		"intent": 1.1,
		"collection": "all",
		"landing": (("product", 0.58), ("/en/products", 0.34), ("/en", 0.08)),
	},
	{
		"key": "google-cpc",
		"utm_source": "google",
		"utm_medium": "cpc",
		"utm_campaign": "brand-search",
		"referrer": "https://www.google.com/",
		"base_share": 0.14,
		"campaign": None,
		"devices": (("Mobile", 0.55), ("Desktop", 0.38), ("Tablet", 0.07)),
		"hours": WORKDAY_HOURS,
		"weekend_lift": 0.9,
		"intent": 1.5,
		"collection": "bestsellers",
		"landing": (("/en", 0.45), ("/en/products", 0.45), ("product", 0.10)),
	},
	{
		"key": "newsletter",
		"utm_source": "newsletter",
		"utm_medium": "email",
		"utm_campaign": "end-of-season-sale",
		"referrer": None,
		"base_share": 0.03,
		"campaign": None,
		"devices": (("Desktop", 0.54), ("Mobile", 0.38), ("Tablet", 0.08)),
		"hours": MORNING_HOURS,
		"weekend_lift": 0.7,
		"intent": 1.6,
		"collection": "featured",
		"landing": (("/en/products", 0.70), ("product", 0.30)),
	},
	{
		"key": "whatsapp-diwali",
		"utm_source": "whatsapp",
		"utm_medium": "social",
		"utm_campaign": "diwali",
		"referrer": "https://wa.me/",
		"base_share": 0.0,
		"campaign": "diwali",
		"devices": (("Mobile", 0.92), ("Tablet", 0.05), ("Desktop", 0.03)),
		"hours": EVENING_HOURS,
		"weekend_lift": 1.25,
		"intent": 1.15,
		"collection": "gifting",
		"landing": (("/en/products", 0.62), ("product", 0.38)),
	},
	{
		"key": "instagram-diwali",
		"utm_source": "instagram",
		"utm_medium": "social",
		"utm_campaign": "diwali",
		"referrer": "https://l.instagram.com/",
		"base_share": 0.0,
		"campaign": "diwali",
		"devices": (("Mobile", 0.90), ("Tablet", 0.06), ("Desktop", 0.04)),
		"hours": EVENING_HOURS,
		"weekend_lift": 1.3,
		"intent": 1.2,
		"collection": "gifting",
		"landing": (("product", 0.66), ("/en/products", 0.34)),
	},
	{
		"key": "instagram-holi",
		"utm_source": "instagram",
		"utm_medium": "social",
		"utm_campaign": "holi",
		"referrer": "https://l.instagram.com/",
		"base_share": 0.0,
		"campaign": "holi",
		"devices": (("Mobile", 0.90), ("Tablet", 0.06), ("Desktop", 0.04)),
		"hours": EVENING_HOURS,
		"weekend_lift": 1.3,
		"intent": 1.05,
		"collection": "edit",
		"landing": (("product", 0.60), ("/en/products", 0.40)),
	},
	{
		"key": "facebook-diwali",
		"utm_source": "facebook",
		"utm_medium": "paid",
		"utm_campaign": "diwali",
		"referrer": "https://l.facebook.com/",
		"base_share": 0.0,
		"campaign": "diwali",
		"devices": (("Mobile", 0.78), ("Desktop", 0.15), ("Tablet", 0.07)),
		"hours": EVENING_HOURS,
		"weekend_lift": 1.15,
		"intent": 1.3,
		"collection": "bestsellers",
		"landing": (("/en/products", 0.66), ("product", 0.34)),
	},
)
CAMPAIGN_CHANNEL_SHARE = 0.22
NEWSLETTER_SEND_WEEKDAY = 1
NEWSLETTER_SEND_SHARE = 0.16

EVENT_COLUMNS = (
	"name",
	"creation",
	"modified",
	"modified_by",
	"owner",
	"docstatus",
	"idx",
	"event",
	"session_id",
	"visitor_user",
	"device",
	"item_code",
	"qty",
	"value",
	"currency",
	"order_id",
	"path",
	"referrer",
	"items_json",
	"utm_source",
	"utm_medium",
	"utm_campaign",
)
CLEARED_ATTRIBUTION = {
	"custom_analytics_session_id": None,
	"custom_utm_source": None,
	"custom_utm_medium": None,
	"custom_utm_campaign": None,
}


def get_campaign_windows(start_date, end_date):
	"""Festival campaigns clustered into contiguous bursts inside the seeded window."""
	return {
		"holi": (add_days(end_date, -30), add_days(end_date, -20)),
		"diwali": (add_days(end_date, -16), end_date),
	}


def ensure_demo_site(confirm_production):
	"""Refuse to scribble demo traffic over a site that looks like production."""
	site = frappe.local.site or ""
	looks_like_test = cint(frappe.conf.developer_mode) or site.endswith((".localhost", ".test"))
	if looks_like_test or cint(confirm_production):
		return
	frappe.throw(
		_(
			"{0} does not look like a test site (developer_mode is off and the site name is not"
			" .localhost or .test). Re-run with --kwargs '{{\"confirm_production\": 1}}' if you"
			" really mean to seed demo analytics here."
		).format(site)
	)


def get_company():
	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw(_("No Company exists — run the ERPNext setup wizard first."))
	return company


def get_selling_price_list(company_currency):
	"""A price list in company currency keeps grand_total == base_grand_total.

	The KPI tiles sum base_grand_total while the purchase event carries grand_total.
	"""
	price_list = frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1, "currency": company_currency}, "name"
	)
	if not price_list:
		frappe.throw(
			_("No enabled selling Price List in {0} — create one before seeding demo analytics.").format(
				company_currency
			)
		)
	return price_list


def get_ecommerce_warehouse(company):
	"""Same warehouse the storefront checkout stamps on its orders."""
	warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
	return warehouse or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


def get_catalog():
	"""Published storefront products, each with its real size item codes and catalog price."""
	variants = frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1},
		fields=["name", "route", "display_name"],
		order_by="name",
	)
	if not variants:
		frappe.throw(_("No published Style Attribute Variants — run install_demo_data first."))
	size_rows = frappe.get_all(
		"Color Size Item",
		filters={"parent": ("in", [variant.name for variant in variants])},
		fields=["parent", "item_code"],
		order_by="parent asc, idx asc",
	)
	item_codes = [row.item_code for row in size_rows if row.item_code]
	live_item_codes = set(
		frappe.get_all("Item", filters={"name": ("in", item_codes), "disabled": 0}, pluck="name")
	)
	price_rows = frappe.get_all(
		"Item Price",
		filters={"item_code": ("in", list(live_item_codes)), "price_list": CATALOG_PRICE_LIST},
		fields=["item_code", "price_list_rate"],
	)
	price_by_item = {row.item_code: flt(row.price_list_rate) for row in price_rows}
	codes_by_variant = {}
	for row in size_rows:
		if row.item_code in live_item_codes:
			codes_by_variant.setdefault(row.parent, []).append(row.item_code)

	catalog = []
	for variant in variants:
		codes = codes_by_variant.get(variant.name) or []
		if not codes:
			continue
		price = next((price_by_item[code] for code in codes if price_by_item.get(code)), FALLBACK_PRICE)
		catalog.append(
			{
				"route": variant.route,
				"path": f"/en/products/{variant.route}",
				"display_name": variant.display_name,
				"item_codes": codes,
				"price": price,
			}
		)
	if not catalog:
		frappe.throw(_("Published products have no live size items — nothing to seed analytics against."))
	return catalog


def get_collections(catalog, rng):
	"""Rank products once, then hand each channel a slice — so views and orders tell one story."""
	ranked = catalog[:]
	rng.shuffle(ranked)
	count = len(ranked)
	collections = {
		"all": ranked,
		"bestsellers": ranked[: max(6, count // 3)],
		"gifting": ranked[: max(8, count // 2)],
		"featured": ranked[: max(10, (count * 2) // 3)],
		"edit": ranked[count // 5 :][: max(8, count // 2)] or ranked,
	}
	return collections, ranked


def pick_weighted(rng, pairs):
	return rng.choices([pair[0] for pair in pairs], weights=[pair[1] for pair in pairs])[0]


def get_active_channels(day, campaign_windows):
	active = []
	for channel in CHANNELS:
		share = channel["base_share"]
		campaign = channel["campaign"]
		if campaign:
			window_from, window_to = campaign_windows[campaign]
			if not (window_from <= day <= window_to):
				continue
			share = CAMPAIGN_CHANNEL_SHARE
		if channel["key"] == "newsletter" and day.weekday() == NEWSLETTER_SEND_WEEKDAY:
			share = NEWSLETTER_SEND_SHARE
		active.append((channel, share * (channel["weekend_lift"] if day.weekday() >= 5 else 1.0)))
	return active


def get_sessions_for_day(day, day_index):
	# a gentle upward trend keeps the "vs previous period" deltas positive but not absurd
	trend = 1.0 + (day_index / HISTORY_DAYS) * GROWTH_OVER_WINDOW
	weekend_lift = 1.22 if day.weekday() >= 5 else 1.0
	return int(BASE_SESSIONS_PER_DAY * trend * weekend_lift)


def get_item_modifiers(product, hero_route, quiet_route):
	"""Two deliberate outliers that make the engagement widget worth reading."""
	if product["route"] == hero_route:
		return 0.06, 0.7
	if product["route"] == quiet_route:
		return 2.4, 1.6
	return 1.0, 1.0


class Clock:
	"""Strictly increasing timestamps: get_landing_pages joins on MIN(creation), so ties double-count."""

	def __init__(self, started_at, rng):
		self.now = started_at
		self.rng = rng

	def next(self, seconds=None):
		gap = self.rng.randint(20, 240) if seconds is None else seconds
		self.now = add_to_date(self.now, seconds=gap)
		return self.now


class SessionPlan:
	def __init__(self, session_id, channel, device, visitor_user, started_at):
		self.session_id = session_id
		self.channel = channel
		self.device = device
		self.visitor_user = visitor_user
		self.shopper = None
		self.started_at = started_at
		self.last_at = started_at
		self.events = []
		self.cart = []
		self.cart_value = 0.0
		self.purchased = False
		self.purchase_at = None
		self.order_name = None
		self.order_total = 0.0


def add_view(plan, clock, product, item_code):
	plan.events.append(
		{
			"event": "view_item",
			"at": clock.next(),
			"path": product["path"],
			"item_code": item_code,
			"product": product,
		}
	)


def add_cart_row(rng, plan, clock, product, item_code):
	qty = pick_weighted(rng, ((1, 0.85), (2, 0.15)))
	amount = flt(product["price"] * qty, 2)
	plan.cart.append({"item_code": item_code, "qty": qty, "price": product["price"], "amount": amount})
	plan.cart_value = flt(plan.cart_value + amount, 2)
	plan.events.append(
		{
			"event": "add_to_cart",
			"at": clock.next(),
			"path": product["path"],
			"item_code": item_code,
			"qty": qty,
			"value": amount,
		}
	)


def build_session(rng, plan, products, hero_route, quiet_route):
	"""One shopper's whole visit — the item viewed is the item carted is the item bought."""
	channel = plan.channel
	clock = Clock(plan.started_at, rng)
	landing_choice = pick_weighted(rng, channel["landing"])
	landing_product = rng.choice(products) if landing_choice == "product" else None
	plan.events.append(
		{
			"event": "page_view",
			"at": plan.started_at,
			"path": landing_product["path"] if landing_product else landing_choice,
			"referrer": channel["referrer"],
		}
	)
	if rng.random() < 0.45:
		plan.events.append({"event": "page_view", "at": clock.next(), "path": "/en/products"})

	if rng.random() > min(MAX_STEP_RATE, VIEW_ITEM_RATE * channel["intent"]):
		plan.last_at = clock.now
		return

	viewed = [landing_product] if landing_product else []
	hero_weights = [HERO_VIEW_WEIGHT if product["route"] == hero_route else 1.0 for product in products]
	for _attempt in range(pick_weighted(rng, ((1, 0.6), (2, 0.3), (3, 0.1)))):
		product = rng.choices(products, weights=hero_weights)[0]
		if product not in viewed:
			viewed.append(product)
	# the size chosen on the product page is the size that goes into the cart
	item_code_by_route = {product["route"]: rng.choice(product["item_codes"]) for product in viewed}
	for product in viewed:
		add_view(plan, clock, product, item_code_by_route[product["route"]])

	add_boost, purchase_boost = get_item_modifiers(viewed[0], hero_route, quiet_route)
	if rng.random() > min(MAX_STEP_RATE, ADD_TO_CART_RATE * channel["intent"] * add_boost):
		plan.last_at = clock.now
		return

	for product in viewed[: pick_weighted(rng, ((1, 0.75), (2, 0.25)))]:
		add_cart_row(rng, plan, clock, product, item_code_by_route[product["route"]])

	if rng.random() > min(MAX_STEP_RATE, BEGIN_CHECKOUT_RATE * channel["intent"]):
		plan.last_at = clock.now
		return
	plan.events.append({"event": "page_view", "at": clock.next(), "path": "/en/cart"})
	plan.events.append(
		{
			"event": "begin_checkout",
			"at": clock.next(),
			"path": "/en/cart/checkout",
			"value": plan.cart_value,
			"items": plan.cart,
		}
	)
	if rng.random() > min(MAX_STEP_RATE, PURCHASE_RATE * channel["intent"] * purchase_boost):
		plan.last_at = clock.now
		return
	plan.purchased = True
	plan.purchase_at = clock.next()
	plan.last_at = clock.now


def build_day_plans(rng, day, day_index, context):
	active = get_active_channels(day, context["campaign_windows"])
	plans = []
	cutoff = context["cutoff"]
	# today is only part-elapsed, so its sessions squeeze into the hours that have already happened.
	# Whole hours: randint over a varying range consumes varying bits and desyncs the seeded stream.
	hours = (list(range(cutoff.hour)) or [0]) if cutoff else list(range(24))
	for sequence in range(get_sessions_for_day(day, day_index)):
		channel = pick_weighted(rng, active)
		hour = rng.choices(hours, weights=channel["hours"][: len(hours)])[0]
		last_minute = MAX_SESSION_MINUTES if hour == LAST_HOUR_OF_DAY else 59
		started_at = get_datetime(
			f"{day} {hour:02d}:{rng.randint(0, last_minute):02d}:{rng.randint(0, 59):02d}"
		)
		shopper = rng.choice(context["customers"]) if rng.random() < LOGGED_IN_SHARE else None
		plan = SessionPlan(
			f"{SESSION_PREFIX}{day_index:03d}-{sequence:04d}",
			channel,
			pick_weighted(rng, channel["devices"]),
			shopper["email"] if shopper else None,
			started_at,
		)
		plan.shopper = shopper
		build_session(
			rng,
			plan,
			context["collections"][channel["collection"]],
			context["hero_route"],
			context["quiet_route"],
		)
		plans.append(plan)
	return plans


def build_live_session(rng, plan, products, stop_after):
	"""Live View reads the last 5 and 10 minutes, so a checkout must carry its own earlier add_to_cart."""
	clock = Clock(plan.started_at, rng)
	product = rng.choice(products)
	item_code = rng.choice(product["item_codes"])
	plan.events.append({"event": "page_view", "at": plan.started_at, "path": "/en", "referrer": None})
	if stop_after == "page_view":
		plan.last_at = clock.now
		return
	add_view(plan, clock, product, item_code)
	if stop_after == "view_item":
		plan.last_at = clock.now
		return
	add_cart_row(rng, plan, clock, product, item_code)
	if stop_after == "add_to_cart":
		plan.last_at = clock.now
		return
	plan.events.append(
		{
			"event": "begin_checkout",
			"at": clock.next(20),
			"path": "/en/cart/checkout",
			"value": plan.cart_value,
			"items": plan.cart,
		}
	)
	if stop_after == "begin_checkout":
		plan.last_at = clock.now
		return
	plan.purchased = True
	plan.purchase_at = clock.next(20)
	plan.last_at = clock.now


def build_live_plans(rng, context):
	now = now_datetime()
	plans = []
	stages = (
		(9, "begin_checkout"),
		(7, "purchase"),
		(4, "add_to_cart"),
		(2, "page_view"),
		(1, "view_item"),
	)
	for index, (minutes_ago, stop_after) in enumerate(stages):
		channel = CHANNELS[index % len(CHANNELS)]
		shopper = context["customers"][index] if index % 2 else None
		plan = SessionPlan(
			f"{SESSION_PREFIX}live-{index:02d}",
			channel,
			pick_weighted(rng, channel["devices"]),
			shopper["email"] if shopper else None,
			add_to_date(now, minutes=-minutes_ago),
		)
		plan.shopper = shopper
		build_live_session(rng, plan, context["collections"]["bestsellers"], stop_after)
		plans.append(plan)
	return plans


def create_demo_customers():
	customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	customers = []
	for index in range(1, DEMO_CUSTOMER_COUNT + 1):
		customer_name = f"{DEMO_CUSTOMER_PREFIX} {index:02d}"
		name = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
		if not name:
			customer = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": customer_name,
					"customer_type": "Individual",
					"customer_group": customer_group,
					"territory": territory,
				}
			).insert(ignore_permissions=True)
			name = customer.name
		customers.append({"name": name, "email": f"demo.shopper.{index:02d}@example.com"})
	return customers


def get_attribution(session_id, channel):
	return {
		"custom_analytics_session_id": session_id,
		"custom_utm_source": channel["utm_source"],
		"custom_utm_medium": channel["utm_medium"],
		"custom_utm_campaign": channel["utm_campaign"],
	}


def create_sales_order(customer, transaction_date, items, context, attribution, placed_at):
	sales_order = frappe.new_doc("Sales Order")
	sales_order.customer = customer
	sales_order.company = context["company"]
	sales_order.order_type = "Shopping Cart"
	sales_order.transaction_date = transaction_date
	sales_order.delivery_date = add_days(transaction_date, 3)
	sales_order.currency = context["currency"]
	sales_order.conversion_rate = 1
	sales_order.selling_price_list = context["price_list"]
	sales_order.plc_conversion_rate = 1
	sales_order.ignore_pricing_rule = 1
	sales_order.set_warehouse = context["warehouse"]
	for row in items:
		sales_order.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": row["qty"],
				"rate": row["price"],
				"price_list_rate": row["price"],
				"warehouse": context["warehouse"],
				"delivery_date": add_days(transaction_date, 3),
			},
		)
	sales_order.update(attribution)
	sales_order.insert(ignore_permissions=True)
	# the sales heatmap buckets on creation, so the order must look placed at checkout time.
	frappe.db.set_value("Sales Order", sales_order.name, "creation", placed_at, update_modified=False)
	return sales_order


def create_orders_for_plans(plans, context, rng):
	orders = 0
	for plan in plans:
		if not plan.purchased:
			continue
		# a guest checkout still ends up on a customer record, so pick one either way
		customer = plan.shopper or rng.choice(context["customers"])
		sales_order = create_sales_order(
			customer["name"],
			getdate(plan.purchase_at),
			plan.cart,
			context,
			get_attribution(plan.session_id, plan.channel),
			plan.purchase_at,
		)
		plan.order_name = sales_order.name
		plan.order_total = flt(sales_order.grand_total, 2)
		orders += 1
	return orders


def create_prior_history_orders(context, rng):
	today = getdate(now_datetime())
	for index in range(PRIOR_HISTORY_ORDERS):
		transaction_date = add_days(today, rng.randint(PRIOR_HISTORY_FROM_DAY, PRIOR_HISTORY_TO_DAY))
		product = rng.choice(context["catalog"])
		items = [{"item_code": rng.choice(product["item_codes"]), "qty": 1, "price": product["price"]}]
		placed_at = get_datetime(f"{transaction_date} {rng.randint(9, 21):02d}:{rng.randint(0, 59):02d}:00")
		create_sales_order(
			context["customers"][index % len(context["customers"])]["name"],
			transaction_date,
			items,
			context,
			get_attribution(f"{SESSION_PREFIX}hist-{index:03d}", CHANNELS[0]),
			placed_at,
		)


def create_recoverable_quotations(plans, context, rng):
	"""A draft Quotation with a contact_email is what promotes an abandoned cart to Recoverable."""
	candidates = [plan for plan in plans if plan.cart and not plan.purchased and not plan.visitor_user]
	candidates.sort(key=lambda plan: plan.last_at, reverse=True)
	created = 0
	# only every other recent guest cart gets a quotation, so the widget still shows plain Abandoned rows
	for plan in candidates[: RECOVERABLE_QUOTATIONS * 2 : 2]:
		customer = rng.choice(context["customers"])
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		quotation.party_name = customer["name"]
		quotation.company = context["company"]
		quotation.order_type = "Shopping Cart"
		quotation.transaction_date = getdate(plan.last_at)
		quotation.valid_till = add_days(getdate(plan.last_at), 14)
		quotation.currency = context["currency"]
		quotation.conversion_rate = 1
		quotation.selling_price_list = context["price_list"]
		quotation.plc_conversion_rate = 1
		quotation.ignore_pricing_rule = 1
		quotation.set_warehouse = context["warehouse"]
		quotation.contact_email = customer["email"]
		for row in plan.cart:
			quotation.append(
				"items",
				{
					"item_code": row["item_code"],
					"qty": row["qty"],
					"rate": row["price"],
					"price_list_rate": row["price"],
					"warehouse": context["warehouse"],
				},
			)
		quotation.update(get_attribution(plan.session_id, plan.channel))
		quotation.insert(ignore_permissions=True)
		frappe.db.set_value("Quotation", quotation.name, "creation", plan.last_at, update_modified=False)
		created += 1
	return created


def get_items_snapshot(items):
	return json.dumps(
		[
			{"item_code": row["item_code"], "qty": cint(row["qty"]), "price": flt(row["price"])}
			for row in items
		]
	)


def get_event_row(index, timestamp, plan, event, currency):
	channel = plan.channel
	value = flt(event.get("value"))
	return (
		f"{EVENT_NAME_PREFIX}{index:09d}",
		timestamp,
		timestamp,
		"Administrator",
		"Administrator",
		0,
		1,
		event["event"],
		plan.session_id,
		plan.visitor_user,
		plan.device,
		event.get("item_code"),
		cint(event.get("qty")),
		value,
		currency if value else None,
		event.get("order_id"),
		event.get("path"),
		event.get("referrer"),
		get_items_snapshot(event["items"]) if event.get("items") else None,
		channel["utm_source"],
		channel["utm_medium"],
		channel["utm_campaign"],
	)


def get_event_rows(plans, currency, start_index):
	rows = []
	index = start_index
	for plan in plans:
		for event in plan.events:
			index += 1
			rows.append(get_event_row(index, event["at"], plan, event, currency))
		if plan.purchased and plan.order_name:
			index += 1
			purchase = {
				"event": "purchase",
				"value": plan.order_total,
				"order_id": plan.order_name,
				"path": "/en/account/orders/confirmation",
				"items": plan.cart,
			}
			rows.append(get_event_row(index, plan.purchase_at, plan, purchase, currency))
	return rows, index


def stamp_existing_orders(order_names):
	"""The orders that were already on the site get attribution too.

	No purchase event is written: events.py already logged one, and a second would double their revenue.
	"""
	for position, name in enumerate(sorted(order_names)):
		frappe.db.set_value(
			"Sales Order",
			name,
			get_attribution(f"{LEGACY_SESSION_PREFIX}{position:03d}", CHANNELS[position % len(CHANNELS)]),
			update_modified=False,
		)
	return len(order_names)


def get_existing_webshop_orders():
	return frappe.get_all("Sales Order", filters={"order_type": "Shopping Cart"}, pluck="name")


@data_source("demo_data")
def install_analytics_demo_data(confirm_production=0):
	"""Seed ~60 days of storefront analytics events, orders, and abandoned carts."""
	ensure_demo_site(confirm_production)
	remove_analytics_demo_data(confirm_production=1, quiet=True)

	rng = random.Random(RANDOM_SEED)
	company = get_company()
	currency = frappe.get_cached_value("Company", company, "default_currency")
	catalog = get_catalog()
	collections, ranked = get_collections(catalog, rng)
	now = now_datetime()
	end_date = getdate(now)
	start_date = add_days(end_date, -(HISTORY_DAYS - 1))
	context = {
		"company": company,
		"currency": currency,
		"price_list": get_selling_price_list(currency),
		"warehouse": get_ecommerce_warehouse(company),
		"catalog": catalog,
		"collections": collections,
		"hero_route": ranked[0]["route"],
		"quiet_route": ranked[-3]["route"] if len(ranked) > 3 else ranked[-1]["route"],
		"customers": create_demo_customers(),
		"campaign_windows": get_campaign_windows(start_date, end_date),
		"cutoff": None,
	}
	existing_orders = get_existing_webshop_orders()

	print(f"Seeding {HISTORY_DAYS} days of storefront analytics ({start_date} to {end_date})")
	plans = []
	for day_index in range(HISTORY_DAYS):
		day = add_days(start_date, day_index)
		context["cutoff"] = add_to_date(now, minutes=-LIVE_TAIL_MARGIN_MINUTES) if day == end_date else None
		plans.extend(build_day_plans(rng, day, day_index, context))
	plans.extend(build_live_plans(rng, context))

	converted = sum(1 for plan in plans if plan.purchased)
	print(f"Creating Sales Orders for {converted} converted sessions")
	orders = create_orders_for_plans(plans, context, rng)
	create_prior_history_orders(context, rng)
	quotations = create_recoverable_quotations(plans, context, rng)

	rows, _index = get_event_rows(plans, currency, 0)
	stamped = stamp_existing_orders(existing_orders)
	# ponytail: bulk_insert bypasses the ORM (no hooks, no per-row validation) because this writes
	# tens of thousands of append-only log rows; switch back to insert() if the doctype ever grows
	# a controller with real behaviour
	frappe.db.bulk_insert("Storefront Analytics Event", EVENT_COLUMNS, rows)
	# nosemgrep: frappe-manual-commit  # seeder, runs from the console or a long background job
	frappe.db.commit()

	print(
		f"Done: {len(rows)} events, {len(plans)} sessions, {orders} orders,"
		f" {PRIOR_HISTORY_ORDERS} prior-history orders, {quotations} draft quotations,"
		f" {stamped} pre-existing orders stamped"
	)
	print(
		"Undo with: bench --site <site> execute"
		" commera.install_analytics_demo_data.remove_analytics_demo_data"
	)


def remove_analytics_demo_data(confirm_production=0, quiet=False):
	"""Delete everything install_analytics_demo_data created and unstamp what it only touched."""
	ensure_demo_site(confirm_production)
	frappe.db.delete("Storefront Analytics Event", {"name": ("like", f"{EVENT_NAME_PREFIX}%")})
	for doctype in ("Quotation", "Sales Order"):
		seeded = frappe.get_all(
			doctype, filters={"custom_analytics_session_id": ("like", f"{SESSION_PREFIX}%")}, pluck="name"
		)
		for name in seeded:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
		frappe.db.set_value(
			doctype,
			{"custom_analytics_session_id": ("like", f"{LEGACY_SESSION_PREFIX}%")},
			CLEARED_ATTRIBUTION,
			update_modified=False,
		)
	for name in frappe.get_all(
		"Customer", filters={"customer_name": ("like", f"{DEMO_CUSTOMER_PREFIX}%")}, pluck="name"
	):
		frappe.delete_doc("Customer", name, force=True, ignore_permissions=True, delete_permanently=True)
	# nosemgrep: frappe-manual-commit  # teardown script, runs outside a request
	frappe.db.commit()
	if not quiet:
		print("Removed storefront analytics demo data")
