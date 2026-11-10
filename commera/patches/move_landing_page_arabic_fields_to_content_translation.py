"""Copy the Landing Page Settings Arabic GIFs, banner, hero banners and their links into Arabic Content
Translation rows, then delete them. Arabic hero banner N translates English hero banner N."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields
from frappe.utils import cstr

from commera.patches.legacy_arabic import Archive, TranslationCopy, commit, has_value, read_existing

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
BANNER_FIELDS = ("banner_image", "url")
ARCHIVE_PREFIX = "legacy-landing-page-arabic-unmigrated"
ARCHIVE_TITLE = "Landing Page Settings Arabic values archived before the fields were dropped"
ARCHIVE_HEADER = ("field", "hero_banner_position", "value", "reason")


def execute():
	migration = LandingPageArabicMigration()
	if migration.values or migration.banners:
		migration.run()
	delete_custom_fields({LANDING_PAGE: [*FIELDS, TABLE]})
	frappe.db.delete("Property Setter", {"doc_type": LANDING_PAGE, "field_name": ("in", [*FIELDS, TABLE])})
	frappe.db.delete("Singles", {"doctype": LANDING_PAGE, "field": ("in", list(FIELDS))})
	frappe.db.delete(BANNER, {"parenttype": LANDING_PAGE, "parentfield": TABLE})
	frappe.clear_document_cache(LANDING_PAGE, LANDING_PAGE)


class LandingPageArabicMigration:
	"""A Single is one record, so its values are read at once. What cannot be copied goes to an archive."""

	def __init__(self):
		self.values = read_singles(list(FIELDS))
		self.banners = read_banners(TABLE)
		self.archive = Archive(
			ARCHIVE_PREFIX, ARCHIVE_TITLE, ARCHIVE_HEADER, "Landing Page Settings Arabic values"
		)

	def run(self):
		self.copy_fields()
		self.copy_banners()
		self.archive.save()
		commit()

	def copy_fields(self):
		copy = TranslationCopy(LANDING_PAGE)
		sources = read_singles(list(FIELDS.values()))
		existing = read_existing(LANDING_PAGE, [LANDING_PAGE], list(FIELDS.values()))
		for column, raw in self.values.items():
			field = FIELDS[column]
			reasons = copy.add(LANDING_PAGE, field, raw, sources.get(field), existing)
			if reasons:
				self.archive.add(column, "", raw, "; ".join(reasons))
		copy.insert()

	def copy_banners(self):
		copy = TranslationCopy(BANNER)
		targets = read_banners(SOURCE_TABLE)
		existing = read_existing(BANNER, [row.name for row in targets], list(BANNER_FIELDS))
		for position, row in enumerate(self.banners, start=1):
			target = targets[position - 1] if position <= len(targets) else None
			for field in BANNER_FIELDS:
				raw = cstr(row.get(field))
				if target:
					reasons = copy.add(target.name, field, raw, target.get(field), existing)
				else:
					reasons = ["no English hero banner at this position"] if raw else []
				if reasons:
					self.archive.add(f"{TABLE}.{field}", position, raw, "; ".join(reasons))
		copy.insert()


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
		.select(banner.name, *(banner[field] for field in BANNER_FIELDS))
		.where(
			(banner.parent == LANDING_PAGE)
			& (banner.parenttype == LANDING_PAGE)
			& (banner.parentfield == table)
		)
		.orderby(banner.idx)
		.orderby(banner.name)
		.run(as_dict=True)
	)
