"""Write the localization of each page and the Python url() of each case into url-cases.json.
Add a page or a case, then from the bench sites folder run ../env/bin/python <this> <site>, then biome format."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import get_localization, url
from commera.localization.languages import StorefrontLanguages

CASES_FILE = Path(__file__).resolve().parents[1] / "packages" / "storefront" / "test" / "url-cases.json"


def main(site: str):
	frappe.init(site)
	frappe.connect()
	try:
		# A dev script: generates the cases as a guest sees them, never on a live request.
		frappe.set_user("Guest")  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		cases = json.loads(CASES_FILE.read_text())
		write_cases(cases)
		CASES_FILE.write_text(json.dumps(cases, indent="\t", ensure_ascii=False) + "\n")
	finally:
		frappe.destroy()


def write_cases(cases: dict):
	# The settings stay as they are: the languages of the cases stand in for them.
	with patch.object(StorefrontLanguages, "load", return_value=get_languages(cases["languages"])):
		for page in cases["pages"]:
			open_page(page)
			localization = get_localization()
			cases["pages"][page] = {
				"language": localization.language.code,
				"root_prefix": localization.root_prefix,
				"prefix_codes": list(localization.prefix_codes),
			}
		for case in cases["cases"]:
			open_page(case["page"])
			case["expected"] = url(case["path"])


def get_languages(languages: dict) -> StorefrontLanguages:
	rows = [(code, True) for code in languages["published"]]
	rows += [(code, False) for code in languages.get("unpublished", [])]
	return StorefrontLanguages(languages["default"], rows)


def open_page(path: str):
	frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
	frappe.local.form_dict = frappe._dict()
	frappe.local.request_cache.clear()


if __name__ == "__main__":
	main(sys.argv[1])
