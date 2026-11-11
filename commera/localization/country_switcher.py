"""The countries a shopper can switch to, grouped by market, for the country switcher."""

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils.caching import request_cache

from commera.localization.markets import Market
from commera.localization.resolver import get_localization
from commera.localization.urls import switch_url


@dataclass(frozen=True)
class CountryChoice:
	name: str
	url: str
	is_current: bool


@dataclass(frozen=True)
class MarketChoices:
	market: Market
	# None for the primary market: its one choice already names it.
	title: str | None
	countries: tuple[CountryChoice, ...]


def get_country_choices() -> list[MarketChoices]:
	"""Each enabled market with its countries, named in the page language, the primary market first.
	Empty when the store has one market: it needs no switcher."""
	localization = get_localization()
	markets = localization.available_markets
	if len(markets) < 2:
		return []
	names = get_country_names(tuple(code for market in markets for code in market.countries))
	return [
		get_primary_choices(market, names) if market.is_primary else get_market_choices(market, names)
		for market in markets
	]


def get_market_place() -> str:
	"""Where the shopper buys, in the page language: the country the URL names, else the market."""
	localization = get_localization()
	country = localization.country
	names = get_country_names((country,)) if country else {}
	return _(names.get(country) or localization.market.title)


def get_primary_choices(market: Market, names: dict[str, str]) -> MarketChoices:
	"""One choice for every country that no other market claims."""
	localization = get_localization()
	choice = CountryChoice(
		name=get_primary_label(set(names.values())),
		url=switch_url(market=market.handle),
		is_current=bool(localization.market and localization.market.is_primary),
	)
	return MarketChoices(market=market, title=None, countries=(choice,))


def get_market_choices(market: Market, names: dict[str, str]) -> MarketChoices:
	localization = get_localization()
	current = localization.market and localization.market.handle == market.handle
	choices = [
		CountryChoice(
			name=_(names[code]),
			url=switch_url(country=code),
			is_current=bool(current and localization.country == code),
		)
		for code in market.countries
		if code in names
	]
	return MarketChoices(
		market=market,
		title=_(market.title),
		countries=tuple(sorted(choices, key=lambda choice: choice.name.casefold())),
	)


def get_primary_label(claimed: set[str]) -> str:
	"""The store company's country, unless another market claims it."""
	country = get_store_country()
	return _(country) if country and country not in claimed else _("Other countries")


def get_store_country() -> str | None:
	from commera.utils import get_store_company

	company = get_store_company()
	return company and frappe.get_cached_value("Company", company, "country")


@request_cache
def get_country_names(codes: tuple[str, ...]) -> dict[str, str]:
	"""Lowercase ISO code to Country name. The header and the mobile menu both ask."""
	if not codes:
		return {}
	rows = frappe.get_all("Country", filters={"code": ["in", list(codes)]}, fields=["name", "code"])
	return {row.code.lower(): row.name for row in rows if row.code}
