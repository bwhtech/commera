import frappe
from frappe import _
from frappe.utils.caching import redis_cache
from frappe.utils.data import cstr, flt

from commera.shipping.rates import get_live_quotes, get_open_rate_profiles, get_rate_details, get_rate_request

SERVICE_FIELDS = [
	"name",
	"title",
	"description",
	"provider",
	"service_code",
	"carrier",
	"markup_percent",
	"handling_fee",
	"backup_charge",
]

# Sentinel for a service that cannot be priced for this destination. Not None or 0.0, so a
# caller cannot mistake it for free.
UNPRICEABLE = object()

SERVICES_CACHE_TTL_SECONDS = 60 * 60


@redis_cache(ttl=SERVICES_CACHE_TTL_SECONDS)
def get_enabled_services() -> list[dict]:
	# Read on every checkout render. Shipping Service.on_update/on_trash clear this.
	return frappe.get_all(
		"Shipping Service",
		filters={"enabled": 1},
		fields=SERVICE_FIELDS,
		order_by="creation asc",
	)


def find_service(title: str) -> dict | None:
	"""Look up a service by title, enabled or not: payment must price a selection disabled mid-checkout."""
	return frappe.db.get_value("Shipping Service", title, SERVICE_FIELDS, as_dict=True)


def quote_services(
	origin: dict | None,
	destination: dict,
	parcels: list[dict],
	cart: dict,
	cod: bool = False,
	shipping_rule: str | None = None,
) -> list[dict]:
	"""Price every enabled Shipping Service for this cart: Shipping Rule band, else live rate, else
	Backup Charge, then add the rates of carriers set to offer all of them. Never raises."""
	services = get_enabled_services()
	open_profiles = get_open_rate_profiles()
	if not (services or open_profiles):
		return []

	request = get_rate_request(origin, destination, parcels, cart, cod)
	providers = [service["provider"] for service in services if service.get("provider")] + open_profiles
	rates_by_provider = get_live_quotes(providers, request)
	quotes = {
		(provider, cstr(rate.get("service_code"))): rate
		for provider, rates in rates_by_provider.items()
		for rate in rates
	}

	rule = get_shipping_rule(shipping_rule)
	bands_by_service = get_rule_bands(rule)
	band_value = get_band_value(rule, cart)
	rows = [
		price_row(
			service,
			quotes.get(quote_key(service)),
			cart,
			get_covering_band(bands_by_service.get(service["name"]), band_value),
		)
		for service in services
	]
	rows += get_open_rate_rows(rates_by_provider, open_profiles, services, cart)
	return [row for row in rows if row is not None]


def has_delivery_options() -> bool:
	return bool(get_enabled_services() or get_open_rate_profiles())


def quote_key(service: dict) -> tuple:
	return (service.get("provider"), cstr(service.get("service_code")))


def get_open_rate_rows(
	rates_by_provider: dict, open_profiles: list[str], services: list[dict], cart: dict
) -> list[dict | None]:
	"""A row per rate that no Shipping Service covers, titled like Shopify: carrier, then service."""
	covered = {quote_key(service) for service in services}
	return [
		get_open_rate_row(provider, rate, cart)
		for provider in open_profiles
		for rate in rates_by_provider.get(provider, [])
		if (provider, cstr(rate.get("service_code"))) not in covered
	]


def get_open_rate_row(provider: str, rate: dict, cart: dict) -> dict | None:
	amount = get_live_amount({}, rate, cart)
	if amount is None:
		return None
	return {
		"title": f"{provider} {rate.get('service_name') or rate.get('service_code')}",
		"description": cstr(rate.get("description")),
		"provider": provider,
		"service_code": cstr(rate.get("service_code")),
		"amount": amount,
		"is_free": not amount,
		"is_live_rate": True,
		**get_rate_details(rate),
	}


def price_row(service: dict, quote: dict | None, cart: dict, band=None) -> dict | None:
	priced = price_service(service, quote, cart, band)
	if priced is UNPRICEABLE:
		return None
	amount, is_live_rate = priced
	return {
		"title": service["title"],
		"description": cstr(service.get("description") or (quote or {}).get("description")),
		"provider": service.get("provider"),
		"service_code": cstr(service.get("service_code")),
		"amount": amount,
		# The storefront gates its "Free" label on this: any zero final amount is free.
		"is_free": not amount,
		"is_live_rate": is_live_rate,
		# A band or backup price still ships with the carrier, so its window and phone rule apply.
		**get_rate_details(quote or {}),
	}


def price_service(service: dict, quote: dict | None, cart: dict, band=None):
	"""(amount, is_live_rate) for this service, or UNPRICEABLE when nothing prices it for this cart."""
	if band is not None:
		if band.free_shipping:
			return 0.0, False
		# Shipping Rule bands are in COMPANY currency, the same as ERPNext's
		# add_shipping_rule_to_tax_table assumes; convert back to what the cart is priced in.
		return flt(flt(band.shipping_amount) / get_conversion_rate(cart), 2), False

	live_amount = get_live_amount(service, quote, cart)
	if live_amount is not None:
		return live_amount, True

	backup_charge = flt(service.get("backup_charge"), 2)
	if backup_charge > 0:
		return backup_charge, False
	return UNPRICEABLE


def get_shipping_rule(shipping_rule: str | None):
	if not shipping_rule:
		return None
	try:
		rule = frappe.get_cached_doc("Shipping Rule", shipping_rule)
	except frappe.DoesNotExistError:
		return None
	return None if rule.disabled else rule


def get_rule_bands(rule) -> dict[str, list]:
	"""The rule's bands grouped by Shipping Service. Bands with no service are left to ERPNext."""
	bands = {}
	for condition in rule.conditions if rule else []:
		if condition.shipping_service:
			bands.setdefault(condition.shipping_service, []).append(condition)
	return bands


def get_band_value(rule, cart: dict) -> float:
	# ERPNext's ShippingRule.apply brackets a Net Weight rule on total weight and every other rule on
	# base_net_total, so a weight rule must never be matched against the cart's value.
	if rule and rule.calculate_based_on == "Net Weight":
		return flt(cart.get("weight"))
	return flt(cart.get("base_net_total"))


def get_covering_band(bands: list | None, value: float):
	"""The band that brackets `value`, or None. A `to_value` of 0 means "and above"."""
	for band in bands or []:
		if flt(band.from_value) <= value and (not band.to_value or value <= flt(band.to_value)):
			return band
	# Deliberately no fallback band: a cart outside every band falls through to the Backup Charge rather
	# than shipping free. ERPNext allows one open-ended band per rule, so only one service can be "and above".
	return None


def get_conversion_rate(cart: dict) -> float:
	return flt(cart.get("conversion_rate")) or 1.0


def get_live_amount(service: dict, quote: dict | None, cart: dict) -> float | None:
	"""The marked-up live carrier amount, or None when there is no usable quote."""
	if not quote:
		return None

	amount = convert_to_cart_currency(flt(quote.get("amount")), quote.get("currency"), cart)
	if amount is None:
		# A quote in a currency we cannot convert today. Charging the number verbatim would bill rupees as
		# riyals, so the option falls back to its backup charge instead.
		return None

	marked_up = amount * (1 + flt(service.get("markup_percent")) / 100) + flt(service.get("handling_fee"))
	return flt(marked_up, 2)


def convert_to_cart_currency(amount: float, currency: str | None, cart: dict) -> float | None:
	cart_currency = cart.get("currency")
	if not currency or not cart_currency or currency == cart_currency:
		return amount

	# Imported lazily: this is the only line in the pricing engine that needs erpnext, and a rate lookup
	# failing must not stop the module loading.
	from erpnext.setup.utils import get_exchange_rate

	try:
		conversion = flt(get_exchange_rate(currency, cart_currency))
	except Exception:
		conversion = 0.0
	if not conversion:
		frappe.log_error(
			title="Shipping rate conversion failed",
			message=f"No exchange rate {currency} -> {cart_currency}",
		)
		return None
	return amount * conversion


def get_charge_amount(
	title: str,
	cart: dict,
	quoted_amount: float | None = None,
	shipping_rule: str | None = None,
) -> float:
	"""What to bill for a chosen delivery option. `quoted_amount` must come from server-side storage.
	Without it the option is re-priced, and a live-rate-only option fails loudly."""
	if quoted_amount is not None:
		return flt(quoted_amount, 2)

	service = find_service(title)
	if service is None:
		frappe.throw(
			_("Delivery option {0} no longer exists, and no quoted amount was stored for it.").format(title)
		)

	rule = get_shipping_rule(shipping_rule)
	band = get_covering_band(get_rule_bands(rule).get(service["name"]), get_band_value(rule, cart))
	priced = price_service(service, None, cart, band)
	if priced is UNPRICEABLE:
		frappe.throw(
			_(
				"Delivery option {0} cannot be priced for this order. Set a Backup Charge on it, or a"
				" band on the store's Shipping Rule that covers this cart."
			).format(title)
		)
	amount, _is_live_rate = priced
	return flt(amount, 2)


def get_charge_account(shipping_rule: str | None) -> str | None:
	"""The account a delivery fee should post against: the store's Shipping Rule account, else None so the
	caller falls back to its own default."""
	if not shipping_rule:
		return None
	return frappe.get_cached_value("Shipping Rule", shipping_rule, "account")
