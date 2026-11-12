import copy
import csv
import io
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import translations as translations_api
from commera.api.admin.theme import activate_theme
from commera.api.admin.theme_layout import get_editor
from commera.localization import (
	CURRENT,
	MISSING,
	OUTDATED,
	exchange,
	exchange_job,
	get_translatable_resource,
	register,
)
from commera.roles import COMMERA_ADMIN, COMMERA_USER, add_commera_roles
from commera.tests.test_admin_theme_layout import publish
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_market_translation import set_up_market_translations
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.tests.test_theme_section_translation import ARABIC_HEADING, ENTRY, HEADING, SUMMER_THEME

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
		set_up_market_translations(self)
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

	def test_a_row_for_a_market_that_does_not_exist_is_an_error(self):
		report = exchange.import_csv(to_csv([self.row("title", "ملاحظة", Market="nowhere")]), "ar")

		self.assertEqual(len(report.errors), 1)
		self.assertIn("Market nowhere does not exist", report.errors[0]["message"])
		self.assertEqual(translations_of(self.note.name), [])

	def test_rows_for_an_unknown_record_or_field_are_errors_even_when_empty(self):
		rows = [
			self.row("title", "", Identification="no-such-note"),
			self.row("route", ""),
			self.row("content", "", Identification=self.make_note("Gift note").name),
		]

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [2, 3])
		self.assertIn("no-such-note", report.errors[0]["message"])
		self.assertIn("route", report.errors[1]["message"])
		self.assertEqual((report.updated, report.skipped), (0, 1))

	def test_a_translation_whose_source_was_cleared_is_still_exchanged(self):
		register("Note", self.note.name, "content", "ar", "<p>لفها جيدا</p>")
		register("Note", self.note.name, "content", "ar", "<p>لفها للخليج</p>", market="gulf")
		market_only = self.make_note("Gift note", "<p>A gift</p>")
		register("Note", market_only.name, "content", "ar", "<p>هدية</p>", market="gulf")
		for name in (self.note.name, market_only.name):
			frappe.db.set_value("Note", name, "content", "")
		before = translations_of(self.note.name), translations_of(market_only.name)

		content = exchange.export_csv("ar")
		report = exchange.import_csv(content, "ar")

		cells = ("Market", "Status", "Default content", "Translated content")
		self.assertEqual(
			[tuple(row[cell] for cell in cells) for row in self.rows_of(content, field="content")],
			[
				("", OUTDATED, "", self.stored(self.note.name, "content")),
				("gulf", OUTDATED, "", self.stored(self.note.name, "content", "gulf")),
			],
		)
		self.assertEqual(
			[tuple(row[cell] for cell in cells) for row in self.rows_of(content, market_only.name)],
			[
				("", MISSING, market_only.title, ""),
				("gulf", OUTDATED, "", self.stored(market_only.name, "content", "gulf")),
			],
		)
		self.assertEqual((report.updated, report.errors), (0, []))
		self.assertEqual((translations_of(self.note.name), translations_of(market_only.name)), before)

	def test_a_market_row_is_stored_against_its_market(self):
		rows = [self.row("title", "ملاحظة الخليج", Market="Gulf"), self.row("title", "x", Market="XYZ")]

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3])
		stored = [(row.market, row.translated_value) for row in translations_of(self.note.name)]
		self.assertEqual(stored, [("gulf", "ملاحظة الخليج")])

	def test_market_spellings_are_one_key(self):
		rows = [self.row("title", "أولى", Market="GULF"), self.row("title", "ثانية", Market="gulf")]

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3])
		stored = [(row.market, row.translated_value) for row in translations_of(self.note.name)]
		self.assertEqual(stored, [("gulf", "أولى")])

	def test_a_primary_market_row_is_the_shop_wide_row(self):
		rows = [self.row("title", "أولى", Market="primary"), self.row("title", "ثانية")]

		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual([error["row"] for error in report.errors], [3])
		stored = [(row.market, row.translated_value) for row in translations_of(self.note.name)]
		self.assertEqual(stored, [("", "أولى")])

	def test_a_disabled_market_row_is_imported(self):
		report = exchange.import_csv(to_csv([self.row("title", "ملاحظة", Market="levant")]), "ar")

		self.assertEqual((report.updated, report.errors), (1, []))
		self.assertEqual(self.stored(self.note.name, market="levant"), "ملاحظة")

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
		register("Note", self.note.name, "title", "ar", "ملاحظة الخليج", market="gulf")
		frappe.db.set_value("Note", self.note.name, "title", "Packing note v2")
		register("Note", self.note.name, "title", "ar", "ملاحظة")

		content = exchange.export_csv("ar")
		rows = self.rows_of(content, self.note.name)
		unchanged = exchange.import_csv(content, "ar")
		rows[1]["Translated content"] = "ملاحظة الخليج الجديدة"
		report = exchange.import_csv(to_csv(rows), "ar")

		self.assertEqual(
			[(row["Field"], row["Market"], row["Status"], row["Translated content"]) for row in rows],
			[
				("title", "", CURRENT, "ملاحظة"),
				("title", "gulf", OUTDATED, "ملاحظة الخليج الجديدة"),
				("content", "", MISSING, ""),
			],
		)
		self.assertEqual((unchanged.updated, unchanged.errors), (0, []))
		self.assertEqual((report.updated, report.errors), (1, []))
		self.assertEqual(self.stored(self.note.name, market="gulf"), "ملاحظة الخليج الجديدة")
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

	def test_only_a_storefront_language_is_exchanged(self):
		with self.assertRaises(frappe.ValidationError):
			exchange.export_csv("fr")
		with self.assertRaises(frappe.ValidationError):
			exchange.import_csv(to_csv([self.row("title", "x", Locale="fr")]), "fr")

	def test_the_default_language_exchanges_market_rows_only(self):
		register("Note", self.note.name, "title", "en", "Gulf packing note", market="gulf")
		rows = [
			self.row("title", "Shop-wide note", Locale="en"),
			self.row("title", "Gulf note", Locale="en", Market="gulf"),
		]

		exported = self.rows_of(exchange.export_csv("en"))
		report = exchange.import_csv(to_csv(rows), "en")

		self.assertEqual(
			[(row["Field"], row["Market"], row["Translated content"]) for row in exported],
			[("title", "gulf", "Gulf packing note")],
		)
		self.assertEqual(report.updated, 1)
		self.assertEqual([error["row"] for error in report.errors], [2])
		filters = {"reference_name": self.note.name, "language": "en"}
		stored = frappe.get_all("Content Translation", filters, ["market", "translated_value"])
		self.assertEqual([(row.market, row.translated_value) for row in stored], [("gulf", "Gulf note")])

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

	def test_an_import_reindexes_its_records_in_one_search_job(self):
		other = self.make_note("Gift note")
		rows = [self.row("title", "ملاحظة"), self.row("title", "هدية", Identification=other.name)]

		with (
			patch("commera.search.translations.is_search_title", return_value=True),
			patch("frappe.enqueue") as enqueue,
		):
			exchange.import_csv(to_csv(rows), "ar")

		search_jobs = [call for call in enqueue.call_args_list if call.args[0].startswith("commera.search.")]
		self.assertEqual(len(search_jobs), 1)
		self.assertEqual(search_jobs[0].args[0], "commera.search.sync.upsert_docs")
		self.assertEqual(search_jobs[0].kwargs["queue"], "long")
		self.assertCountEqual(search_jobs[0].kwargs["names"], [self.note.name, other.name])

	def test_a_large_import_runs_as_a_background_job(self):
		file = self.upload([self.row("title", "ملاحظة"), self.row("content", "<p>لفها جيدا</p>")])

		with (
			patch.object(exchange_job, "REQUEST_IMPORT_ROWS", 1),
			patch.object(exchange_job.frappe, "enqueue") as enqueue,
		):
			answer = translations_api.import_translations(file.file_url, "ar")

		self.assertTrue(answer["queued"])
		self.assertIsNone(self.stored(self.note.name))
		job = enqueue.call_args.kwargs
		self.assertEqual((job["queue"], job["job_id"]), ("long", answer["job_id"]))
		with patch.object(exchange_job, "is_job_enqueued", return_value=True):
			self.assertEqual(translations_api.get_import_status(answer["job_id"])["status"], "queued")

		exchange_job.run_import(job["file_name"], job["language"], job["import_id"])

		status = translations_api.get_import_status(answer["job_id"])
		self.assertEqual((status["status"], status["report"]["updated"]), ("done", 2))
		self.assertEqual(self.stored(self.note.name), "ملاحظة")

	def test_a_queued_import_whose_job_is_gone_has_failed(self):
		job_id = exchange_job.queue_import("missing-file", "ar")["job_id"]

		self.assertEqual(translations_api.get_import_status(job_id)["status"], "failed")

	def test_another_users_import_status_is_hidden(self):
		job_id = exchange_job.queue_import("missing-file", "ar")["job_id"]
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(make_user(COMMERA_ADMIN))

		with self.assertRaises(frappe.DoesNotExistError):
			translations_api.get_import_status(job_id)

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


class TestThemeSectionTranslationExchange(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "page": "index"})
		use_storefront_languages(self, "en", published=("en", "ar"))
		activate_theme(SUMMER_THEME)
		hooks = frappe.get_hooks("commera_hooks", {})
		themes = [entry for entry in hooks["translatable_resources"] if entry["type"] == "theme_section"]
		self.enterContext(self.patch_hooks({"commera_hooks": {**hooks, "translatable_resources": themes}}))
		self.resource = get_translatable_resource("theme_section")

	def heading_row(self, content):
		(row,) = [
			row for row in parse(content) if (row["Identification"], row["Field"]) == (ENTRY, "heading")
		]
		return row

	def test_a_theme_section_translation_exports_and_imports_back(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		content = exchange.export_csv("ar")
		row = self.heading_row(content)
		unchanged = exchange.import_csv(content, "ar")
		report = exchange.import_csv(to_csv([{**row, "Translated content": "سترة جديدة"}]), "ar")

		self.assertEqual(
			(row["Type"], row["Status"], row["Default content"], row["Translated content"]),
			("theme_section", CURRENT, HEADING, ARABIC_HEADING),
		)
		self.assertEqual((unchanged.updated, unchanged.errors), (0, []))
		self.assertEqual((report.updated, report.errors), (1, []))
		(entry,) = self.resource.list_entries("ar", filters={"name": ENTRY, "field": "heading"}).entries
		self.assertEqual((entry.value, entry.status), ("سترة جديدة", CURRENT))

	def test_a_theme_section_row_for_a_market_is_an_error(self):
		set_up_market_translations(self)
		row = self.heading_row(exchange.export_csv("ar"))

		report = exchange.import_csv(to_csv([{**row, "Market": "gulf", "Translated content": "x"}]), "ar")

		self.assertEqual(len(report.errors), 1)
		self.assertIn("per market", report.errors[0]["message"])

	def test_a_translation_whose_source_was_cleared_is_still_exchanged(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		layout = copy.deepcopy(get_editor(SUMMER_THEME)["draft_layout"])
		layout["sections"][0]["blocks"][0]["settings"]["heading"] = {"en": "", "ar": ARABIC_HEADING}
		publish(SUMMER_THEME, "index", layout)
		before = frappe.db.get_value("Theme Layout", {"theme": SUMMER_THEME, "page": "index"}, "modified")

		content = exchange.export_csv("ar")
		row = self.heading_row(content)
		report = exchange.import_csv(content, "ar")

		self.assertEqual(
			(row["Status"], row["Default content"], row["Translated content"]), (OUTDATED, "", ARABIC_HEADING)
		)
		self.assertEqual((report.updated, report.errors), (0, []))
		after = frappe.db.get_value("Theme Layout", {"theme": SUMMER_THEME, "page": "index"}, "modified")
		self.assertEqual(after, before)

	def test_a_theme_section_row_for_an_unknown_setting_is_an_error_even_when_empty(self):
		row = self.heading_row(exchange.export_csv("ar"))

		report = exchange.import_csv(
			to_csv([{**row, "Field": "no_such_setting", "Translated content": ""}]), "ar"
		)

		self.assertEqual([error["row"] for error in report.errors], [2])
		self.assertEqual(report.skipped, 0)


SINGLE = "Website Settings"
SINGLE_RESOURCE = {"type": "site", "doctype": SINGLE, "fields": ["app_name", "title_prefix"], "label": "Site"}


class TestSingleTranslationExchange(IntegrationTestCase):
	"""A Single has no rows: its one record is named after the doctype."""

	def setUp(self):
		frappe.db.savepoint("single_translation_test")
		self.addCleanup(frappe.db.rollback, save_point="single_translation_test")
		use_storefront_languages(self, "en", published=("en", "ar"))
		hooks = {**frappe.get_hooks("commera_hooks", {}), "translatable_resources": [SINGLE_RESOURCE]}
		self.enterContext(self.patch_hooks({"commera_hooks": hooks}))
		self.set_source("app_name", "ZZ Shop")
		self.set_source("title_prefix", "ZZ Prefix")
		self.resource = get_translatable_resource("site")

	def set_source(self, field, value):
		frappe.db.set_single_value(SINGLE, field, value)

	def keys(self, entries):
		return [(entry.name, entry.field) for entry in entries]

	def test_its_fields_list_by_page_filter_and_search(self):
		first = self.resource.list_entries("ar", limit=1)
		second = self.resource.list_entries("ar", cursor=first.next_cursor, limit=1)

		self.assertEqual(self.keys(first.entries), [(SINGLE, "app_name")])
		self.assertEqual(self.keys(second.entries), [(SINGLE, "title_prefix")])
		self.assertIsNone(second.next_cursor)
		self.assertEqual(self.resource.list_entries("ar", filters={"name": "Other"}).entries, [])
		found = self.resource.list_entries("ar", filters={"name": SINGLE}, search="zz prefix")
		self.assertEqual(self.keys(found.entries), [(SINGLE, "title_prefix")])

	def test_its_statuses_are_counted_from_the_document(self):
		self.resource.write(SINGLE, "app_name", "ar", "متجر")
		self.assertEqual(self.resource.count_statuses("ar"), {MISSING: 1, OUTDATED: 0, CURRENT: 1})

		self.set_source("app_name", "ZZ Store")

		self.assertEqual(self.resource.count_statuses("ar"), {MISSING: 1, OUTDATED: 1, CURRENT: 0})

	def test_it_exports_and_imports_back(self):
		self.resource.write(SINGLE, "app_name", "ar", "متجر")

		content = exchange.export_csv("ar")
		rows = {(row["Identification"], row["Field"]): row for row in parse(content)}
		unchanged = exchange.import_csv(content, "ar")
		edited = {**rows[(SINGLE, "title_prefix")], "Translated content": "بادئة"}
		report = exchange.import_csv(to_csv([edited]), "ar")

		self.assertEqual(list(rows), [(SINGLE, "app_name"), (SINGLE, "title_prefix")])
		self.assertEqual(rows[(SINGLE, "app_name")]["Status"], CURRENT)
		self.assertEqual((unchanged.updated, unchanged.errors), (0, []))
		self.assertEqual((report.updated, report.errors), (1, []))
		(entry,) = self.resource.list_entries("ar", filters={"field": "title_prefix"}).entries
		self.assertEqual((entry.value, entry.status), ("بادئة", CURRENT))

	def test_a_translation_whose_source_was_cleared_is_still_exchanged(self):
		self.resource.write(SINGLE, "title_prefix", "ar", "بادئة")
		self.set_source("title_prefix", "")

		rows = {(row["Identification"], row["Field"]): row for row in parse(exchange.export_csv("ar"))}

		cleared = rows[(SINGLE, "title_prefix")]
		self.assertEqual(
			(cleared["Status"], cleared["Default content"], cleared["Translated content"]),
			(OUTDATED, "", "بادئة"),
		)
