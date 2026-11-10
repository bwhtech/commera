import csv
import io
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import translations as translations_api
from commera.localization import CURRENT, MISSING, OUTDATED, exchange, register
from commera.roles import COMMERA_ADMIN, COMMERA_USER, add_commera_roles
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

NOTE_RESOURCE = {"type": "note", "doctype": "Note", "fields": ["title", "content"], "label": "Notes"}


def parse(content: str) -> list[dict]:
	return list(csv.DictReader(io.StringIO(content.removeprefix("﻿"))))


def to_csv(rows: list[dict]) -> str:
	buffer = io.StringIO()
	writer = csv.DictWriter(buffer, fieldnames=exchange.COLUMNS)
	writer.writeheader()
	writer.writerows(rows)
	return buffer.getvalue()


def make_user(role: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": f"translator-{frappe.generate_hash(length=6)}@example.com",
				"first_name": "Translator",
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		.insert()
		.name
	)


def translations_of(name: str) -> list[dict]:
	return frappe.get_all(
		"Content Translation",
		filters={"reference_name": name},
		fields=["reference_field", "market", "translated_value", "source_hash", "modified"],
		order_by="reference_field asc, market asc",
	)


class TestTranslationExchange(IntegrationTestCase):
	"""Notes stand in for a store's resources, so an export holds only what a test made."""

	def setUp(self):
		# Each test exports every note: keep one test's notes and markets out of the next.
		frappe.db.savepoint("translation_exchange_test")
		self.addCleanup(frappe.db.rollback, save_point="translation_exchange_test")
		use_storefront_languages(self, "en", published=("en", "ar"))
		hooks = {**frappe.get_hooks("commera_hooks", {}), "translatable_resources": [NOTE_RESOURCE]}
		self.enterContext(self.patch_hooks({"commera_hooks": hooks}))
		self.note = self.make_note("Packing note", "<p>Wrap it well</p>")

	def make_note(self, title, content="", name=None):
		title = f"{title} {frappe.generate_hash(length=6)}"
		return frappe.get_doc({"doctype": "Note", "title": title, "content": content}).insert(set_name=name)

	def stored(self, name, field="title", market=""):
		filters = {"reference_name": name, "reference_field": field, "language": "ar", "market": market}
		return frappe.db.get_value("Content Translation", filters, "translated_value")

	def rows_of(self, content, name=None, field=None):
		rows = [row for row in parse(content) if row["Identification"] == (name or self.note.name)]
		return [row for row in rows if field in (None, row["Field"])]

	def row(self, field, translated, **overrides):
		return {
			"Type": "note",
			"Identification": self.note.name,
			"Field": field,
			"Locale": "ar",
			"Market": "",
			"Translated content": translated,
			**overrides,
		}

	def test_export_writes_each_field_in_shopifys_columns(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة التغليف")

		content = exchange.export_csv("ar")

		self.assertEqual(content.splitlines()[0], ",".join(exchange.COLUMNS))
		title, body = self.rows_of(content)
		self.assertEqual(
			title,
			{
				"Type": "note",
				"Identification": self.note.name,
				"Field": "title",
				"Locale": "ar",
				"Market": "",
				"Status": CURRENT,
				"Default content": self.note.title,
				"Translated content": "ملاحظة التغليف",
			},
		)
		self.assertEqual(
			(body["Field"], body["Status"], body["Translated content"]), ("content", MISSING, "")
		)

	def test_export_then_import_without_changes_changes_nothing(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة التغليف")
		register("Note", self.note.name, "content", "ar", "<p>لفها جيدا</p>")
		frappe.db.set_value("Note", self.note.name, "content", "<p>Wrap it twice</p>")
		before = translations_of(self.note.name)

		content = exchange.export_csv("ar")
		report = exchange.import_csv(content, "ar")

		self.assertEqual((report.updated, report.errors), (0, []))
		self.assertGreaterEqual(report.unchanged, 2)
		self.assertEqual(translations_of(self.note.name), before)
		statuses = [row["Status"] for row in self.rows_of(exchange.export_csv("ar"))]
		self.assertEqual(statuses, [CURRENT, OUTDATED])

	def test_import_reports_each_bad_row_and_writes_the_good_ones(self):
		rows = [
			self.row("title", "ملاحظة"),
			self.row("title", "x", Type="gift card"),
			self.row("route", "x"),
			self.row("title", "x", Identification="no-such-note"),
			self.row("title", "x", Locale="fr"),
			self.row("content", "", Identification=self.make_note("Gift note").name),
			self.row("content", "<p>لفها</p>"),
		]
		messages = len(frappe.local.message_log)

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3, 4, 5, 6])
		self.assertIn("gift card", report.errors[0]["message"])
		self.assertIn("no-such-note", report.errors[2]["message"])
		self.assertEqual((report.updated, report.skipped), (2, 1))
		stored = {row.reference_field: row.translated_value for row in translations_of(self.note.name)}
		self.assertEqual(stored, {"title": "ملاحظة", "content": "<p>لفها</p>"})
		self.assertEqual(len(frappe.local.message_log), messages)

	def test_a_market_row_is_an_error_while_markets_do_not_exist(self):
		report = exchange.import_csv(to_csv([self.row("title", "ملاحظة", Market="gulf")]), "ar")

		self.assertEqual(len(report.errors), 1)
		self.assertIn("Market column empty", report.errors[0]["message"])
		self.assertEqual(translations_of(self.note.name), [])

	def test_a_market_row_is_stored_against_its_market_once_markets_exist(self):
		rows = [self.row("title", "ملاحظة الخليج", Market="INR"), self.row("title", "x", Market="XYZ")]

		# Currency stands in for the market doctype, which ships with markets (#450).
		with patch.object(exchange, "MARKET_DOCTYPE", "Currency"):
			report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3])
		stored = [(row.market, row.translated_value) for row in translations_of(self.note.name)]
		self.assertEqual(stored, [("INR", "ملاحظة الخليج")])

	def test_export_neutralises_formulas_and_import_reads_them_back(self):
		note = self.make_note("=1+1")
		register("Note", note.name, "title", "ar", '=HYPERLINK("https://example.com","x")')
		before = translations_of(note.name)

		content = exchange.export_csv("ar")
		(title,) = [row for row in self.rows_of(content, note.name) if row["Field"] == "title"]
		report = exchange.import_csv(content, "ar")

		self.assertTrue(title["Default content"].startswith("'="))
		self.assertTrue(title["Translated content"].startswith("'=HYPERLINK"))
		self.assertEqual((report.updated, report.errors), (0, []))
		self.assertEqual(translations_of(note.name), before)

	def test_identifications_starting_with_a_formula_character_still_match(self):
		notes = [self.make_note("Card", name=f"{char}S-{frappe.generate_hash(length=6)}") for char in "=+-@'"]
		for note in notes:
			register("Note", note.name, "title", "ar", "بطاقة")

		content = exchange.export_csv("ar")
		rows = [row for note in notes for row in self.rows_of(content, "'" + note.name, "title")]
		unchanged = exchange.import_csv(content, "ar")
		for row in rows:
			row["Translated content"] = "بطاقة هدية"
		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual(len(rows), len(notes))
		self.assertEqual((unchanged.updated, unchanged.errors), (0, []))
		self.assertEqual((report.updated, report.errors), (len(notes), []))
		self.assertEqual({self.stored(note.name) for note in notes}, {"بطاقة هدية"})

	def test_cells_starting_with_a_formula_character_or_a_quote_round_trip_exactly(self):
		values = [f"{char}S-001" for char in ("=", "+", "-", "@", "\t", "\r", "'", "''", "'=")]
		notes = [self.make_note("Card") for _value in values]
		content = exchange.export_csv("ar")
		rows = [row for note in notes for row in self.rows_of(content, note.name, "title")]
		for row, value in zip(rows, values, strict=True):
			row["Translated content"] = "'" + value

		report = exchange.import_csv(to_csv(rows), "ar")
		exported = exchange.export_csv("ar")
		again = exchange.import_csv(exported, "ar")

		self.assertEqual((report.updated, report.errors), (len(values), []))
		self.assertEqual([self.stored(note.name) for note in notes], values)
		self.assertEqual((again.updated, again.errors), (0, []))
		self.assertEqual(exchange.export_csv("ar"), exported)
		cells = [
			row["Translated content"] for note in notes for row in self.rows_of(exported, note.name, "title")
		]
		self.assertEqual(cells, ["'" + value for value in values])

	def test_a_typed_leading_quote_is_kept(self):
		report = exchange.import_csv(to_csv([self.row("title", "'S-001"), self.row("content", "'")]), "ar")

		self.assertEqual((report.updated, report.errors), (2, []))
		self.assertEqual(
			(self.stored(self.note.name), self.stored(self.note.name, "content")), ("'S-001", "'")
		)

	def test_a_repeated_key_is_an_error_and_the_first_row_is_kept(self):
		rows = [
			self.row("title", "B"),
			self.row("title", "A"),
			self.row("title", "C", Locale="AR"),
			self.row("content", "<p>B</p>"),
		]

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3, 4])
		self.assertIn("Row 2", report.errors[0]["message"])
		self.assertEqual((report.updated, self.stored(self.note.name)), (2, "B"))

	def test_a_long_page_body_round_trips(self):
		body = "<p>" + "لفها جيدا " * 20_000 + "</p>"
		note = self.make_note("Long page", content="<p>" + "Wrap it " * 25_000 + "</p>")
		(row,) = [
			row for row in self.rows_of(exchange.export_csv("ar"), note.name) if row["Field"] == "content"
		]
		row["Translated content"] = body

		report = exchange.import_csv(to_csv([row]), "ar")
		again = exchange.import_csv(exchange.export_csv("ar"), "ar")

		self.assertGreater(len(body), 200_000)
		self.assertEqual((report.updated, report.errors), (1, []))
		self.assertEqual(self.stored(note.name, "content"), body)
		self.assertEqual((again.updated, again.errors), (0, []))

	def test_market_translations_are_exported_with_their_market_and_import_back(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة الخليج", market="INR")
		frappe.db.set_value("Note", self.note.name, "title", "Packing note v2")
		register("Note", self.note.name, "title", "ar", "ملاحظة")

		content = exchange.export_csv("ar")
		rows = self.rows_of(content, self.note.name)
		with patch.object(exchange, "MARKET_DOCTYPE", "Currency"):
			unchanged = exchange.import_csv(content, "ar")
			rows[1]["Translated content"] = "ملاحظة الخليج الجديدة"
			report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual(
			[(row["Field"], row["Market"], row["Status"], row["Translated content"]) for row in rows],
			[
				("title", "", CURRENT, "ملاحظة"),
				("title", "INR", OUTDATED, "ملاحظة الخليج الجديدة"),
				("content", "", MISSING, ""),
			],
		)
		self.assertEqual((unchanged.updated, unchanged.errors), (0, []))
		self.assertEqual((report.updated, report.errors), (1, []))
		self.assertEqual(self.stored(self.note.name, market="INR"), "ملاحظة الخليج الجديدة")
		self.assertEqual(self.stored(self.note.name), "ملاحظة")

	def test_imported_html_is_sanitised(self):
		content = "<p>لفها</p><script>alert(1)</script>"

		exchange.import_csv(to_csv([self.row("content", content)]), "ar")

		(stored,) = translations_of(self.note.name)
		self.assertIn("<p>لفها</p>", stored.translated_value)
		self.assertNotIn("<script", stored.translated_value)

	def test_a_file_over_the_row_limit_is_refused_before_any_row_is_written(self):
		rows = [self.row("title", "ملاحظة"), self.row("content", "<p>لفها</p>")]

		with patch.object(exchange, "MAX_IMPORT_ROWS", 1), self.assertRaises(frappe.ValidationError):
			exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual(translations_of(self.note.name), [])

	def test_a_file_without_the_key_columns_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Locale"):
			exchange.import_csv("Type,Identification,Field,Market,Translated content\n", "ar")

	def test_only_a_translated_storefront_language_is_exchanged(self):
		for language in ("en", "fr"):
			with self.assertRaises(frappe.ValidationError):
				exchange.export_csv(language)
			with self.assertRaises(frappe.ValidationError):
				exchange.import_csv(to_csv([self.row("title", "x", Locale=language)]), language)

	def upload(self, rows):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "translations-ar.csv",
				"is_private": 1,
				"content": to_csv(rows).encode(),
			}
		).insert()

	def test_the_admin_api_downloads_a_csv_and_imports_an_uploaded_one(self):
		translations_api.export_translations("ar")
		self.assertEqual(frappe.response["type"], "download")
		self.assertEqual(frappe.response["filename"], "translations-ar.csv")
		self.assertTrue(frappe.response["filecontent"].startswith("﻿"))

		report = translations_api.import_translations(
			self.upload([self.row("title", "ملاحظة")]).file_url, "ar"
		)

		self.assertEqual((report["updated"], report["errors"]), (1, []))

	def test_a_commera_admin_exports_and_imports_translations(self):
		add_commera_roles()
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(make_user(COMMERA_ADMIN))

		translations_api.export_translations("ar")
		report = translations_api.import_translations(
			self.upload([self.row("title", "ملاحظة")]).file_url, "ar"
		)

		self.assertEqual(frappe.response["filename"], "translations-ar.csv")
		self.assertEqual((report["updated"], report["errors"]), (1, []))
		self.assertEqual(self.stored(self.note.name), "ملاحظة")

	def test_the_admin_api_refuses_a_user_without_access_to_translations(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(make_user(COMMERA_USER))

		with self.assertRaises(frappe.PermissionError):
			translations_api.export_translations("ar")
		with self.assertRaises(frappe.PermissionError):
			translations_api.import_translations("/private/files/translations-ar.csv", "ar")


class TestProductTranslationExchange(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"))

	def test_a_product_title_round_trips_through_the_declared_resource(self):
		product = frappe.get_doc(
			"Style Attribute Variant", {"route": self.make_priced_variant("CSV", default_rate=30)}
		)
		register("Style Attribute Variant", product.name, "display_name", "ar", "قميص الكتان")

		rows = [row for row in parse(exchange.export_csv("ar")) if row["Identification"] == product.name]
		(title,) = [row for row in rows if row["Field"] == "display_name"]
		title["Translated content"] = "قميص الكتان الجديد"
		report = exchange.import_csv(to_csv([title]), "ar")

		self.assertEqual((title["Type"], title["Status"]), ("product", CURRENT))
		self.assertEqual((report.updated, report.errors), (1, []))
		stored = frappe.db.get_value(
			"Content Translation",
			{"reference_name": product.name, "reference_field": "display_name", "language": "ar"},
			"translated_value",
		)
		self.assertEqual(stored, "قميص الكتان الجديد")
