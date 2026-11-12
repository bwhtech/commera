from unittest.mock import patch

import frappe
from frappe.model.meta import Meta

from commera.api.admin import translations as translations_api
from commera.localization import CURRENT, MISSING, OUTDATED, register
from commera.localization.content import SOURCE_TEXT_LENGTH
from commera.tests.test_translations_page import TranslationsPageCase


class TestTranslationsPageDetails(TranslationsPageCase):
	"""What the Translations page shows beside a field's status."""

	def stored_source_text(self, note, fieldname):
		return frappe.db.get_value(
			"Content Translation",
			{"reference_doctype": "Note", "reference_name": note.name, "reference_field": fieldname},
			"source_text",
		)

	def save_one(self, note, fieldname, value):
		return self.save({"resource": "note", "name": note.name, "field": fieldname, "value": value})

	def test_saving_keeps_the_source_text_and_an_outdated_field_shows_it(self):
		note = self.make_note("Gift note")
		old_title = note.title
		self.save_one(note, "title", "ملاحظة الهدية")
		self.assertEqual(self.stored_source_text(note, "title"), old_title)

		self.change_title(note)

		title = self.field(note, "title")
		self.assertEqual((title["status"], title["previous_source"]), (OUTDATED, old_title))

	def test_still_correct_moves_the_stored_source_text_to_the_new_source(self):
		note = self.make_note("Gift note")
		self.save_one(note, "title", "ملاحظة الهدية")
		self.change_title(note)

		self.save_one(note, "title", "ملاحظة الهدية")

		self.assertEqual(self.stored_source_text(note, "title"), note.title)
		self.assertEqual(self.field(note, "title")["previous_source"], None)

	def test_a_translation_saved_before_source_texts_shows_only_that_the_source_changed(self):
		note = self.make_note("Gift note")
		register("Note", note.name, "title", "ar", "ملاحظة الهدية")
		frappe.db.set_value(
			"Content Translation", {"reference_name": note.name}, "source_text", None, update_modified=False
		)
		self.change_title(note)

		title = self.field(note, "title")
		self.assertEqual((title["status"], title["previous_source"]), (OUTDATED, None))

	def test_reading_and_saving_before_the_source_text_column_is_migrated(self):
		note = self.make_note("Unmigrated note")
		has_column = type(frappe.local.db).has_column

		def without_source_text(method):
			def fields(meta, *args, **kwargs):
				result = method(meta, *args, **kwargs)
				return (
					[field for field in result if field != "source_text"]
					if meta.name == "Content Translation"
					else result
				)

			return fields

		def column_exists(db, doctype, column):
			return (
				False
				if (doctype, column) == ("Content Translation", "source_text")
				else has_column(db, doctype, column)
			)

		with (
			patch.object(type(frappe.local.db), "has_column", column_exists),
			patch.object(Meta, "get_valid_fields", without_source_text(Meta.get_valid_fields)),
			patch.object(Meta, "get_valid_columns", without_source_text(Meta.get_valid_columns)),
		):
			self.save_one(note, "title", "ملاحظة")
			self.change_title(note)
			title = self.field(note, "title")
			self.assertEqual((title["status"], title["previous_source"]), (OUTDATED, None))
			self.save_one(note, "title", "ملاحظة جديدة")
			self.assertEqual(self.field(note, "title")["status"], CURRENT)

	def test_a_record_with_only_sourceless_translations_can_be_found_and_cleared(self):
		before = self.note_counts()
		note = self.make_note("Only source")
		self.save_one(note, "title", "ملاحظة")
		frappe.db.set_value("Note", note.name, {"title": "", "content": ""})

		self.assertEqual(self.note_counts(), before)
		self.assertIn(note.name, self.listed_names(to_do=0))
		self.assertNotIn(note.name, self.listed_names(to_do=1))
		item = self.item(note)
		self.assertEqual(item["to_do"], 0)
		(field,) = item["fields"]
		self.assertEqual((field["field"], field["source_empty"], field["value"]), ("title", True, "ملاحظة"))
		batch = translations_api.get_items("ar", "note", records=[note.name])
		self.assertEqual(batch["items"], [item])

		self.save_one(note, "title", "")
		self.assertEqual(translations_api.get_items("ar", "note", record=note.name)["items"], [])
		self.assertNotIn(note.name, self.listed_names(to_do=0))
		self.assertEqual(self.note_counts(), before)

	def test_the_source_text_is_plain_and_bounded(self):
		note = self.make_note("Long note", f"<p>Wrap &amp; send</p><p>{'x' * 600}</p>")
		short = self.make_note("Short note", "<p>Wrap &amp; send</p>")
		register("Note", note.name, "content", "ar", "<p>لفها</p>")
		register("Note", short.name, "content", "ar", "<p>لفها</p>")

		text = self.stored_source_text(note, "content")

		self.assertEqual(self.stored_source_text(short, "content"), "Wrap & send")
		self.assertEqual(len(text), SOURCE_TEXT_LENGTH)
		self.assertTrue(text.startswith("Wrap & send x"))
		self.assertTrue(text.endswith("…"))

	def test_a_file_field_keeps_no_source_text(self):
		frappe.db.delete("Content Translation", {"reference_doctype": "Landing Page Settings"})
		frappe.db.set_single_value(
			"Landing Page Settings", {"gif_1": "/files/sale.gif", "gif_url_1": "/sale"}
		)
		frappe.clear_document_cache("Landing Page Settings", "Landing Page Settings")

		for field, value in (("gif_1", "/files/sale-ar.gif"), ("gif_url_1", "/ar-sale")):
			register("Landing Page Settings", "Landing Page Settings", field, "ar", value)

		texts = dict(
			frappe.get_all(
				"Content Translation",
				filters={"reference_doctype": "Landing Page Settings", "language": "ar"},
				fields=["reference_field", "source_text"],
				as_list=True,
			)
		)
		self.assertEqual(texts, {"gif_1": None, "gif_url_1": "/sale"})

	def test_a_translation_whose_source_is_now_empty_is_shown_but_not_counted(self):
		note = self.make_note("Packing note", "<p>Wrap it well</p>")
		register("Note", note.name, "title", "ar", "ملاحظة التغليف")
		register("Note", note.name, "content", "ar", "<p>لفها جيدا</p>")
		before = translations_api.get_overview()["counts"]["ar"]["note"]

		# Saving an empty Text Editor stores markup, so empty the source directly.
		frappe.db.set_value("Note", note.name, "content", "")

		after = translations_api.get_overview()["counts"]["ar"]["note"]
		item = self.item(note)
		title, content = item["fields"]
		self.assertEqual(
			{status: after[status] - before[status] for status in (MISSING, OUTDATED, CURRENT)},
			{MISSING: 0, OUTDATED: 0, CURRENT: -1},
		)
		self.assertEqual((item["to_do"], item["outdated"], title["field"]), (0, False, "title"))
		self.assertEqual(
			(
				content["field"],
				content["source"],
				content["value"],
				content["status"],
				content["source_empty"],
			),
			("content", "", "<p>لفها جيدا</p>", CURRENT, True),
		)
		self.assertEqual(content["kind"], "html")
		self.assertIn(note.name, self.listed_names(to_do=0))
		self.assertNotIn(note.name, self.listed_names(to_do=1))

	def test_an_empty_source_without_a_translation_is_not_shown(self):
		note = self.make_note("Packing note")
		register("Note", note.name, "title", "ar", "ملاحظة التغليف")
		frappe.db.set_value("Note", note.name, "content", "")

		self.assertEqual([field["field"] for field in self.item(note)["fields"]], ["title"])

	def listed_names(self, to_do):
		names, cursor = [], None
		while True:
			page = translations_api.get_items("ar", "note", to_do=to_do, cursor=cursor)
			names += [item["name"] for item in page["items"]]
			if not (cursor := page["next_cursor"]):
				return names
