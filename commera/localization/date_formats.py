"""Babel's date patterns of one language, as data. packages/storefront/formatter.js renders them,
so a date reads the same in the browser as Babel prints it on the server."""

from babel import Locale, UnknownLocaleError
from babel.dates import get_day_names, get_era_names, get_month_names, tokenize_pattern

from commera.localization.languages import FALLBACK_LANGUAGE

DATE_STYLES = ("short", "medium", "long", "full")
NAME_WIDTHS = {3: "abbreviated", 4: "wide", 5: "narrow", 6: "short"}


class DateFormats:
	def __init__(self, locale: Locale):
		self.locale = locale

	@classmethod
	def for_language(cls, code: str) -> "DateFormats":
		return cls(get_babel_locale(code))

	def as_dict(self) -> dict:
		"""`parts` per style, and the `names` of each name field the parts use."""
		parts = {style: self.parts(style) for style in DATE_STYLES}
		fields = sorted({part["field"] for style in parts.values() for part in style if "field" in part})
		return {
			"parts": parts,
			"names": {field: self.names(field) for field in fields if is_name_field(field)},
		}

	def parts(self, style: str) -> list[dict]:
		return [
			{"text": value} if kind == "chars" else {"field": value[0] * value[1]}
			for kind, value in tokenize_pattern(self.locale.date_formats[style].pattern)
		]

	def names(self, field: str) -> list[str]:
		"""Eras BC then AD, months from January, weekdays from Monday, as Babel indexes them."""
		char, width = field[0], NAME_WIDTHS[max(3, len(field))]
		if char == "G":
			return [get_era_names(width, locale=self.locale)[era] for era in (0, 1)]
		context = "stand-alone" if char in ("L", "c") else "format"
		if char in ("M", "L"):
			return [get_month_names(width, context, self.locale)[month] for month in range(1, 13)]
		return [get_day_names(width, context, self.locale)[day] for day in range(7)]


def is_name_field(field: str) -> bool:
	"""Babel prints E as a name at any length, and M, L, c and e as numbers below three letters."""
	return field[0] in ("G", "E") or (field[0] in ("M", "L", "c", "e") and len(field) >= 3)


def get_babel_locale(code: str) -> Locale:
	try:
		return Locale.parse(code, sep="-")
	except (UnknownLocaleError, ValueError):
		return Locale.parse(FALLBACK_LANGUAGE)
