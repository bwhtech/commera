"""Copy the Landing Page Settings Arabic GIFs, banner and their links into Arabic Content Translation rows,
move the Arabic hero banners into the hero banner table as Arabic rows, then delete the Arabic fields."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields
from frappe.utils import cstr

from commera.patches.legacy_arabic import (
	LANGUAGE,
	Archive,
	TranslationCopy,
	commit,
	has_value,
	read_existing,
)

LANDING_PAGE = "Landing Page Settings"
BANNER = "Landing Page Hero Banner"
TRANSLATED = (
	*(f"gif_{number}" for number in range(1, 5)),
	*(f"gif_url_{number}" for number in range(1, 5)),
	"banner_1",
	"banner_url_1",
)
# Each Arabic field and the field it translates.
FIELDS = {f"{field}_ar": field for field in TRANSLATED}
TABLE, SOURCE_TABLE = "hero_banner_ar", "hero_banner"
# The link fields' default. An Arabic link left at it, like its English link, translates nothing.
DEFAULT_LINK = "/"
ARCHIVE_PREFIX = "legacy-landing-page-arabic-unmigrated"
ARCHIVE_TITLE = "Landing Page Settings Arabic values archived before the fields were dropped"
ARCHIVE_HEADER = ("field", "value", "reason")


def execute():
	migration = LandingPageArabicMigration()
	if migration.values:
		migration.run()
	move_arabic_banners()
	delete_custom_fields({LANDING_PAGE: [*FIELDS, TABLE]})
	frappe.db.delete("Property Setter", {"doc_type": LANDING_PAGE, "field_name": ("in", [*FIELDS, TABLE])})
	frappe.db.delete("Singles", {"doctype": LANDING_PAGE, "field": ("in", list(FIELDS))})
	frappe.clear_document_cache(LANDING_PAGE, LANDING_PAGE)


class LandingPageArabicMigration:
	"""A Single is one record, so its values are read at once. What cannot be copied goes to an archive."""

	def __init__(self):
		self.values = read_singles(list(FIELDS))
		self.archive = Archive(
			ARCHIVE_PREFIX, ARCHIVE_TITLE, ARCHIVE_HEADER, "Landing Page Settings Arabic values"
		)

	def run(self):
		self.copy_fields()
		self.archive.save()
		commit()

	def copy_fields(self):
		copy = TranslationCopy(LANDING_PAGE)
		sources = read_singles(list(FIELDS.values()))
		existing = read_existing(LANDING_PAGE, [LANDING_PAGE], list(FIELDS.values()))
		for column, raw in self.values.items():
			field = FIELDS[column]
			if raw == DEFAULT_LINK and sources.get(field) == DEFAULT_LINK:
				continue
			if reasons := copy.add(LANDING_PAGE, field, raw, sources.get(field), existing):
				self.archive.add(column, raw, "; ".join(reasons))
		copy.insert()


def move_arabic_banners():
	"""Re-parent the Arabic hero banners into the English table, tagged Arabic, after the English rows.
	The rows themselves are kept, so every value, blank or not, stays byte for byte."""
	english = read_banners(SOURCE_TABLE)
	start = english[-1].idx if english else 0
	banner = frappe.qb.DocType(BANNER)
	for idx, row in enumerate(read_banners(TABLE), start=start + 1):
		(
			frappe.qb.update(banner)
			.set(banner.parentfield, SOURCE_TABLE)
			.set(banner.language, LANGUAGE)
			.set(banner.idx, idx)
			.where(banner.name == row.name)
			.run()
		)


def read_singles(fields: list[str]) -> dict[str, str]:
	"""{field: value} of the Single's stored non-empty values, read past its meta, which lacks the dropped fields."""
	singles = frappe.qb.DocType("Singles")
	rows = (
		frappe.qb.from_(singles)
		.select(singles.field, singles.value)
		.where((singles.doctype == LANDING_PAGE) & singles.field.isin(fields) & has_value(singles.value))
		.run(as_dict=True)
	)
	return {row.field: cstr(row.value) for row in rows}


def read_banners(table: str) -> list:
	"""The hero banner rows of one table field, in their order on the page."""
	banner = frappe.qb.DocType(BANNER)
	return (
		frappe.qb.from_(banner)
		.select(banner.name, banner.idx, banner.banner_image, banner.url, banner.language)
		.where(
			(banner.parent == LANDING_PAGE)
			& (banner.parenttype == LANDING_PAGE)
			& (banner.parentfield == table)
		)
		.orderby(banner.idx)
		.orderby(banner.name)
		.run(as_dict=True)
	)
