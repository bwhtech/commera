"""The countries a shopper may ship to or bill in: those of their market. The primary market takes
every country that no other enabled market claims. A country of another market means a switch."""

from dataclasses import dataclass

import frappe
from frappe import _

from commera.guest import get_guest_cart_key
from commera.localization.country_switcher import get_country_names, get_store_country
from commera.localization.markets import Market, StorefrontMarkets, normalize_country
from commera.localization.resolver import get_localization
from commera.localization.urls import switch_url


class AddressCountryError(frappe.ValidationError):
	pass


@dataclass(frozen=True)
class AddressCountries:
	market: Market
	# The enabled markets: they decide which market claims a country.
	markets: StorefrontMarkets

	@classmethod
	def current(cls) -> "AddressCountries":
		return cls.of(get_localization().market)

	@classmethod
	def of(cls, market: Market | None) -> "AddressCountries":
		"""The countries of `market`, the primary market when None. A disabled market keeps its own."""
		markets = StorefrontMarkets.load()
		return cls(market or markets.primary, markets)

	def allows(self, code: str | None) -> bool:
		code = normalize_country(code)
		if self.market.is_primary:
			return self.markets.for_country(code).is_primary
		return code in self.market.countries

	def within(self, countries: list[dict]) -> list[dict]:
		"""The rows of `countries`, each with an ISO `code`, that this market ships to."""
		return [row for row in countries if self.allows(row.get("code"))]

	def group_others(self, countries: list[dict]) -> list[tuple[Market, list[dict]]]:
		"""The rows of `countries` that other enabled markets ship to, by market, in market order."""
		groups = {market.handle: (market, []) for market in self.markets.all}
		for row in countries:
			if not self.allows(row.get("code")):
				groups[self.markets.for_country(row.get("code")).handle][1].append(row)
		return [(market, rows) for market, rows in groups.values() if rows]

	def validate(self, country: str | None):
		"""Refuse an address in `country`, a Country name, when this market does not ship there."""
		code = frappe.get_cached_value("Country", country, "code") if country else None
		if self.allows(code):
			return
		owner = self.markets.for_country(code)
		frappe.throw(
			_("{0} is in the {1} market. Switch to that market to use this address.").format(
				_(country or ""), _(owner.title)
			),
			AddressCountryError,
			title=_("Country Not Available"),
		)

	def default_country(self) -> str | None:
		"""The Country name a blank address starts with: the URL's country, else the store's."""
		localization = get_localization()
		if not self.market.is_primary:
			code = localization.country if localization.country in self.market.countries else None
			code = code or self.market.countries[0]
			return get_country_names((code,)).get(code)
		country = get_store_country() or frappe.defaults.get_global_default("country")
		code = frappe.get_cached_value("Country", country, "code") if country else None
		return country if self.allows(code) else None


def get_draft_scope() -> str:
	from frappe.utils.data import sha256_hash

	return sha256_hash(f"{frappe.session.user}:{frappe.session.sid}:{get_guest_cart_key() or ''}")


def get_market_switches(other_markets: list[dict]) -> dict:
	"""What a country picker needs to offer a switch, from shop.list_other_market_countries():
	the market of each Country name, and each market's URL for this page and its prompt."""
	prompt = _("{0} is in the {1} market. Switch to shop in {2}?")
	return {
		"draft_scope": get_draft_scope(),
		"countries": {
			country["name"]: group["market"] for group in other_markets for country in group["countries"]
		},
		"markets": {
			group["market"]: {
				"url": switch_url(market=group["market"]),
				# {0} stays for the browser: the country the shopper picks.
				"prompt": prompt.format("{0}", group["title"], group["currency"]),
			}
			for group in other_markets
		},
	}
