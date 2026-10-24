import os

import frappe

from commera.shop_themes.theme_check import ERROR, check_theme, format_findings
from commera.shop_themes.theme_files import find_theme_dirs_on_disk


def assert_theme_valid(theme: str):
	slug = frappe.scrub(theme)
	theme_dirs = find_theme_dirs_on_disk(slug)
	if not theme_dirs or os.path.basename(theme_dirs[0]) != slug:
		raise AssertionError(f"No theme folder with a Shop Theme record for {theme}")
	errors = [finding for finding in check_theme(theme_dirs) if finding["severity"] == ERROR]
	if errors:
		raise AssertionError(f"{theme} theme check found errors:\n{format_findings(errors)}")
