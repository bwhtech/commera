"""Copy each Shop Web Page's Arabic content into an Arabic Content Translation row, then drop the column.
Model sync leaves the column of the removed field in place, so this patch still reads it."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

from commera.localization.content import get_sources
from commera.patches.legacy_arabic import Archive, TranslationCopy, commit, has_value, read_existing

PAGE = "Shop Web Page"
COLUMN = "content_ar"
FIELD = "content"
BATCH_SIZE = 500
ARCHIVE_PREFIX = "legacy-page-arabic-unmigrated"
ARCHIVE_TITLE = "Shop Web Page Arabic content archived before the field was dropped"
ARCHIVE_HEADER = ("page", "route", COLUMN, "reason")


def execute():
	exists = frappe.db.has_column(PAGE, COLUMN)
	if exists:
		WebPageArabicMigration().run()
	delete_custom_fields({PAGE: [COLUMN]})
	frappe.db.delete("Property Setter", {"doc_type": PAGE, "field_name": COLUMN})
	if exists:
		frappe.db.drop_columns(PAGE, [COLUMN])
		# has_column reads a cached column list that MariaDB DDL leaves stale.
		frappe.client_cache.delete_value(f"table_columns::tab{PAGE}")
		frappe.clear_cache(doctype=PAGE)


class WebPageArabicMigration:
	"""Copies the Arabic content one page of pages at a time. What it cannot copy goes to an archive."""

	def __init__(self):
		self.archive = Archive(
			ARCHIVE_PREFIX, ARCHIVE_TITLE, ARCHIVE_HEADER, "Shop Web Pages with Arabic content"
		)

	def run(self):
		for page in self.read_pages():
			self.migrate(page)
		self.archive.save()
		commit()

	def read_pages(self):
		"""Pages with Arabic content, in pages ordered by name."""
		table = frappe.qb.DocType(PAGE)
		query = (
			frappe.qb.from_(table)
			.select(table.name, table.route, table.content, table[COLUMN])
			.where(has_value(table[COLUMN]))
			.orderby(table.name)
			.limit(BATCH_SIZE)
		)
		# The first page has no name bound: a name the collation sorts as "" must not be skipped.
		page = query.run(as_dict=True)
		while page:
			yield page
			page = query.where(table.name > page[-1].name).run(as_dict=True)

	def migrate(self, pages: list):
		copy = TranslationCopy(PAGE)
		sources = get_sources(PAGE, pages, [FIELD])
		existing = read_existing(PAGE, [page.name for page in pages], [FIELD])
		for page, source in zip(pages, sources, strict=True):
			if reasons := copy.add(page.name, FIELD, page[COLUMN], source[FIELD], existing):
				self.archive.add(page.name, page.route, page[COLUMN], "; ".join(reasons))
		copy.insert()
