"""Markets made before market prices sold at the store's prices. Give each the store's price lists:
a market prices like the primary market, so every item keeps its price and availability."""

import frappe

from commera.localization.markets import clear_market_cache


def execute():
	markets = frappe.get_all("Commera Market", filters={"sale_price_list": ("is", "not set")}, pluck="name")
	if not markets:
		return
	price_lists = get_store_price_lists()
	for market in markets:
		if price_lists:
			frappe.db.set_value("Commera Market", market, price_lists, update_modified=False)
		else:
			log_unfilled(market)
	clear_market_cache()


def get_store_price_lists() -> dict | None:
	"""The store's sale list, or its default list when it has no sale list: what the store charges.
	The default list is the compare-at list only beside a sale list in the same currency."""
	settings = frappe.get_cached_doc("Commera Settings")
	selling = [name for name in (settings.sale_price_list, settings.default_price_list) if is_selling(name)]
	if not selling:
		return None
	sale = selling[0]
	currency = frappe.db.get_value("Price List", sale, "currency")
	compare_at = settings.default_price_list if sale == settings.sale_price_list else None
	if compare_at and frappe.db.get_value("Price List", compare_at, "currency") != currency:
		compare_at = None
	return {"sale_price_list": sale, "compare_at_price_list": compare_at, "currency": currency}


def is_selling(price_list: str | None) -> bool:
	return bool(price_list) and bool(frappe.db.get_value("Price List", price_list, "selling"))


def log_unfilled(market: str):
	frappe.log_error(
		title=f"Commera Market {market} has no sale price list",
		message=(
			f"Commera Settings has no selling price list to give market {market}. Until it gets one, the "
			"market sells at the store's prices. Set its Sale Price List under Commera Market."
		),
	)
