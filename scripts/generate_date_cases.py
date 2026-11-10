"""Write the date cases of formatter-cases.json for each Frappe language Babel knows.
After a Babel upgrade: ../env/bin/python scripts/generate_date_cases.py, then biome format."""

import csv
import datetime
import json
import os
from pathlib import Path

import frappe
from babel import Locale, UnknownLocaleError
from babel.dates import format_date

from commera.localization.date_formats import DATE_STYLES, DateFormats

CASES_FILE = Path(__file__).resolve().parents[1] / "packages" / "storefront" / "test" / "formatter-cases.json"
# A Thursday in March, and a Tuesday with a one-digit day and a two-digit year that starts with 0.
DATES = (datetime.date(2026, 3, 5), datetime.date(2009, 12, 1))


def main():
	cases = json.loads(CASES_FILE.read_text())
	locales = dict(get_babel_locales())
	cases["date_formats"] = {code: DateFormats(locale).as_dict() for code, locale in locales.items()}
	cases["date"] = [
		{
			"language": code,
			"value": value.isoformat(),
			"style": style,
			"expected": format_date(value, style, locale=locale),
		}
		for code, locale in locales.items()
		for style in DATE_STYLES
		for value in DATES
	]
	CASES_FILE.write_text(json.dumps(cases, indent="\t", ensure_ascii=False) + "\n")


def get_babel_locales():
	path = os.path.join(os.path.dirname(frappe.__file__), "geo", "languages.csv")
	# A fixed path inside the Frappe package, never user input.
	with open(path, newline="") as languages:  # nosemgrep: frappe-security-file-traversal
		for row in csv.DictReader(languages):
			try:
				yield row["language_code"], Locale.parse(row["language_code"], sep="-")
			except (UnknownLocaleError, ValueError):
				continue


if __name__ == "__main__":
	main()
