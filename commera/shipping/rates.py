import json
import time
from dataclasses import asdict, replace

import frappe
from frappe.utils.data import add_days, cint, cstr, flt, getdate, sha256_hash, today

from commera.shipping.base_class import RateRequest
from commera.shipping.providers import PROFILE_DOCTYPE, get_enabled_profiles, get_provider
from commera.shipping.utils import get_default_origin

# The same windows Shopify uses for carrier-calculated rates: a good answer is reused for 15 minutes,
# a failure for 30 seconds, so one outage does not pin backup prices for long.
RATES_CACHE_TTL_SECONDS = 15 * 60
FAILURE_CACHE_TTL_SECONDS = 30
RATES_CACHE_PREFIX = "commera:carrier_rates:"


class CarrierTimeoutError(Exception):
	pass


def get_rate_request(
	origin: dict | None, destination: dict, parcels: list[dict], cart: dict, cod: bool = False
) -> RateRequest:
	return RateRequest(
		origin=origin or {},
		destination=destination,
		parcels=parcels,
		items=list(cart.get("items") or []),
		currency=cstr(cart.get("currency")),
		locale=cstr(cart.get("locale") or frappe.local.lang),
		subtotal=flt(cart.get("net_total")),
		total=flt(cart.get("grand_total")),
		discount=flt(cart.get("discount_amount")),
		customer=cart.get("customer"),
		customer_group=cart.get("customer_group"),
		cod=cod,
		declared_value=flt(cart.get("declared_value")),
	)


def get_open_rate_profiles() -> list[str]:
	"""Enabled carriers set to offer every rate they return, not only the ones set up as services."""
	return [
		profile
		for profile in get_enabled_profiles()
		if frappe.get_cached_value(PROFILE_DOCTYPE, profile, "offer_all_rates")
	]


def get_live_quotes(providers: list[str], request: RateRequest) -> dict[str, list[dict]]:
	"""Each enabled carrier's rates, one call per carrier. Each ships from its own pickup address unless
	the request names an origin."""
	if not (request.destination and request.parcels):
		return {}

	enabled_profiles = set(get_enabled_profiles())
	return {
		provider: get_provider_rates(provider, request)
		for provider in dict.fromkeys(providers)
		if provider in enabled_profiles
	}


def get_provider_rates(provider: str, request: RateRequest) -> list[dict]:
	"""A slow, broken, unconfigured or unregistered carrier gets no rates, so checkout uses backup pricing."""
	cache_key = f"{RATES_CACHE_PREFIX}{provider}:{get_request_fingerprint(request)}"
	cached = frappe.cache.get_value(cache_key)
	if cached is not None:
		return cached

	try:
		rates, expires_in = call_carrier(provider, request), RATES_CACHE_TTL_SECONDS
	except Exception:
		frappe.log_error(title=f"{provider} checkout rates failed")
		rates, expires_in = [], FAILURE_CACHE_TTL_SECONDS

	frappe.cache.set_value(cache_key, rates, expires_in_sec=expires_in)
	return rates


def call_carrier(provider: str, request: RateRequest) -> list[dict]:
	origin = request.origin or get_default_origin(provider)
	if not origin:
		return []

	started = time.monotonic()
	rates = get_provider(provider).get_rates(replace(request, origin=origin))
	elapsed = time.monotonic() - started
	if elapsed > request.timeout_seconds:
		raise CarrierTimeoutError(f"{provider} answered in {elapsed:.1f}s, over {request.timeout_seconds}s")
	# Normalised here, so a carrier's malformed date counts as its failure rather than breaking checkout.
	return [{**rate, **get_rate_details(rate)} for rate in rates or []]


def get_request_fingerprint(request: RateRequest) -> str:
	fields = asdict(request)
	fields.pop("timeout_seconds")
	return sha256_hash(json.dumps(fields, sort_keys=True, default=str))[:16]


def clear_rates_cache(provider: str | None = None):
	frappe.cache.delete_keys(f"{RATES_CACHE_PREFIX}{provider + ':' if provider else ''}")


def get_rate_details(rate: dict) -> dict:
	"""The delivery window and phone rule a live rate carries. A window comes from transit days when the
	carrier gives no dates."""
	transit_days = cint(rate.get("transit_days"))
	estimate = str(add_days(today(), transit_days)) if transit_days else None
	return {
		"min_delivery_date": get_date(rate.get("min_delivery_date")) or estimate,
		"max_delivery_date": get_date(rate.get("max_delivery_date")) or estimate,
		"phone_required": bool(rate.get("phone_required")),
	}


def get_date(value) -> str | None:
	return str(getdate(value)) if value else None
