import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import translations as translations_api
from commera.api.admin.pages import save_page
from commera.localization import CURRENT, MISSING, OUTDATED, register, translation_items
from commera.roles import COMMERA_ADMIN, COMMERA_USER, add_commera_roles
from commera.tests.test_market_translation import set_up_market_translations
from commera.tests.test_translation_exchange import NOTE_RESOURCE, make_user

PAGE_RESOURCE = {
	"type": "page",
	"doctype": "Shop Web Page",
	"fields": ["title", "content"],
	"label": "Pages",
}
LANDING_RESOURCE = {
	"type": "landing_page",
	"doctype": "Landing Page Settings",
	"fields": ["gif_1", "gif_url_1"],
	"label": "Landing page",
}


class TestTranslationsPage(IntegrationTestCase):
	"""Notes stand in for a store's resources. Other notes on the site may count too, so counts are
	compared before and after a test's own notes."""

	def setUp(self):
		frappe.db.savepoint("translations_page_test")
		self.addCleanup(frappe.db.rollback, save_point="translations_page_test")
		set_up_market_translations(self)
		hooks = {
			**frappe.get_hooks("commera_hooks", {}),
			"translatable_resources": [NOTE_RESOURCE, PAGE_RESOURCE, LANDING_RESOURCE],
		}
		self.enterContext(self.patch_hooks({"commera_hooks": hooks}))

	def make_note(self, title, content=""):
		title = f"{title} {frappe.generate_hash(length=6)}"
		return frappe.get_doc({"doctype": "Note", "title": title, "content": content}).insert()

	def note_counts(self):
		return translations_api.get_overview()["counts"]["ar"]["note"]

	def item(self, note):
		(item,) = translations_api.get_items("ar", "note", record=note.name)["items"]
		return item

	def field(self, note, fieldname):
		return next(field for field in self.item(note)["fields"] if field["field"] == fieldname)

	def change_title(self, note):
		note.title = f"{note.title} changed"
		note.save()

	def save(self, *translations):
		return translations_api.save_translations("ar", json.dumps(translations))

	def test_the_overview_counts_each_status_per_language_and_resource(self):
		before = self.note_counts()
		current = self.make_note("Packing note", "<p>Wrap it well</p>")
		outdated = self.make_note("Gift note", "<p>For you</p>")
		register("Note", current.name, "title", "ar", "ملاحظة التغليف")
		register("Note", outdated.name, "title", "ar", "ملاحظة الهدية")
		self.change_title(outdated)

		overview = translations_api.get_overview()
		after = overview["counts"]["ar"]["note"]

		self.assertEqual([language["code"] for language in overview["languages"]], ["ar"])
		self.assertEqual(overview["source"]["code"], "en")
		self.assertEqual(overview["languages"][0]["direction"], "rtl")
		self.assertIn({"type": "note", "label": "Notes"}, overview["resources"])
		delta = {status: after[status] - before[status] for status in (MISSING, OUTDATED, CURRENT)}
		# Both notes' content is still missing.
		self.assertEqual(delta, {MISSING: 2, OUTDATED: 1, CURRENT: 1})

	def test_an_item_lists_its_fields_with_source_translation_status_and_kind(self):
		note = self.make_note("Packing note", "<p>Wrap it well</p>")
		register("Note", note.name, "title", "ar", "ملاحظة التغليف")

		item = self.item(note)

		self.assertEqual((item["title"], item["to_do"], item["outdated"]), (note.title, 1, False))
		title, content = item["fields"]
		self.assertEqual(
			(title["field"], title["kind"], title["source"], title["value"], title["status"]),
			("title", "text", note.title, "ملاحظة التغليف", CURRENT),
		)
		self.assertEqual((content["field"], content["kind"], content["status"]), ("content", "html", MISSING))
		self.assertIsNone(item["url"])

	def test_pages_return_each_record_once_and_the_to_do_filter_drops_finished_ones(self):
		notes = [self.make_note(f"Note {number}", "<p>Wrap it</p>") for number in range(3)]
		register("Note", notes[1].name, "title", "ar", "ملاحظة")
		register("Note", notes[1].name, "content", "ar", "<p>لفها</p>")

		with patch.object(translation_items, "ITEMS_PER_PAGE", 1):
			all_names, first = self.collect_pages(to_do=0)
			to_do_names, to_do_first = self.collect_pages(to_do=1)

		ours = {note.name for note in notes}
		self.assertEqual(len(all_names), len(set(all_names)))
		self.assertTrue(ours <= set(all_names))
		self.assertEqual(first["total"], len(all_names))
		self.assertEqual(ours & set(to_do_names), {notes[0].name, notes[2].name})
		self.assertEqual(to_do_first["to_do"], len(to_do_names))

	def collect_pages(self, to_do):
		page = translations_api.get_items("ar", "note", to_do=to_do)
		first, names = page, []
		while True:
			names += [item["name"] for item in page["items"]]
			if not page["next_cursor"]:
				return names, first
			self.assertNotIn("total", translations_api.get_items("ar", "note", cursor=page["next_cursor"]))
			page = translations_api.get_items("ar", "note", to_do=to_do, cursor=page["next_cursor"])

	def test_saving_stores_the_current_source_hash_and_clears_outdated(self):
		note = self.make_note("Packing note")
		register("Note", note.name, "title", "ar", "ملاحظة التغليف")
		self.change_title(note)
		self.assertEqual(self.field(note, "title")["status"], OUTDATED)

		# "Still correct": the same text, saved again.
		saved = self.save(
			{"resource": "note", "name": note.name, "field": "title", "value": "ملاحظة التغليف"}
		)

		self.assertEqual(saved, 1)
		self.assertEqual(self.field(note, "title")["status"], CURRENT)

	def test_saving_edits_the_shop_wide_translation_only(self):
		note = self.make_note("Packing note")
		register("Note", note.name, "title", "ar", "ملاحظة الخليج", market="gulf")

		self.save({"resource": "note", "name": note.name, "field": "title", "value": "ملاحظة"})

		rows = frappe.get_all(
			"Content Translation",
			filters={"reference_name": note.name},
			fields=["market", "translated_value"],
			order_by="market asc",
		)
		self.assertEqual(
			[(row.market, row.translated_value) for row in rows], [("", "ملاحظة"), ("gulf", "ملاحظة الخليج")]
		)

	def test_an_empty_value_removes_the_translation(self):
		note = self.make_note("Packing note")
		register("Note", note.name, "title", "ar", "ملاحظة")

		self.save({"resource": "note", "name": note.name, "field": "title", "value": ""})

		self.assertEqual(self.field(note, "title")["status"], MISSING)

	def test_malformed_rows_do_not_delete_or_partially_save(self):
		note = self.make_note("Batch validation")
		register("Note", note.name, "title", "ar", "original")
		valid = {"resource": "note", "name": note.name, "field": "title", "value": "changed"}
		for key in valid:
			for value in (None, 1, []):
				with self.subTest(key=key, value=value):
					with self.assertRaises(frappe.ValidationError):
						self.save(valid, {**valid, key: value})
					self.assertEqual(self.field(note, "title")["value"], "original")
			missing = {field: value for field, value in valid.items() if field != key}
			with self.assertRaises(frappe.ValidationError):
				self.save(valid, missing)
			self.assertEqual(self.field(note, "title")["value"], "original")

	def test_a_later_write_failure_rolls_back_the_batch(self):
		from commera.localization.resources import DoctypeResource

		note = self.make_note("Atomic batch")
		register("Note", note.name, "title", "ar", "original")
		write = DoctypeResource.write
		calls = 0

		def fail_second(resource, *args):
			nonlocal calls
			calls += 1
			if calls == 2:
				raise frappe.ValidationError("second write failed")
			return write(resource, *args)

		row = {"resource": "note", "name": note.name, "field": "title", "value": "changed"}
		with patch.object(DoctypeResource, "write", fail_second):
			with self.assertRaises(frappe.ValidationError):
				self.save(row, row)
		self.assertEqual(self.field(note, "title")["value"], "original")

	def test_catalog_pages_and_search_build_only_bounded_records(self):
		for number in range(120):
			self.make_note(f"Bounded catalog {number}")
		with patch.object(translation_items, "ITEMS_PER_PAGE", 2):
			with patch.object(translation_items, "make_item", wraps=translation_items.make_item) as build:
				page = translations_api.get_items("ar", "note")
				self.assertEqual(build.call_count, 2)
				self.assertGreaterEqual(page["total"], 120)
				self.assertIsNotNone(page["next_cursor"])
		resource = translation_items.get_translatable_resource("note")
		with patch.object(translation_items, "get_translatable_resources", return_value=[resource]):
			with patch.object(translation_items, "iter_matching_names", side_effect=AssertionError("scan")):
				self.assertEqual(
					translations_api.search_translations("ar", frappe.generate_hash(length=20)), []
				)

	def test_the_default_language_is_not_a_target(self):
		with self.assertRaises(frappe.ValidationError):
			translations_api.get_items("en", "note")
		with self.assertRaises(frappe.ValidationError):
			translations_api.save_translations(
				"en", [{"resource": "note", "name": "x", "field": "title", "value": "x"}]
			)

	def test_an_image_without_a_translation_is_not_missing(self):
		frappe.db.delete("Content Translation", {"reference_doctype": "Landing Page Settings"})
		frappe.db.set_single_value(
			"Landing Page Settings", {"gif_1": "/files/sale.gif", "gif_url_1": "/sale"}
		)
		frappe.clear_document_cache("Landing Page Settings", "Landing Page Settings")

		counts = translations_api.get_overview()["counts"]["ar"]["landing_page"]
		(item,) = translations_api.get_items("ar", "landing_page")["items"]

		self.assertEqual((counts[MISSING], counts[CURRENT]), (1, 1))
		statuses = {field["field"]: (field["kind"], field["status"]) for field in item["fields"]}
		self.assertEqual(statuses, {"gif_1": ("image", CURRENT), "gif_url_1": ("text", MISSING)})
		self.assertEqual((item["title"], item["to_do"], item["url"]), ("Landing page", 1, "/ar"))

	def test_a_record_with_a_storefront_page_links_to_it_in_the_language(self):
		page = save_page(title=f"Shipping {frappe.generate_hash(length=6)}", content="<p>Two days</p>")

		(item,) = translations_api.get_items("ar", "page", record=page["name"])["items"]

		self.assertEqual(item["url"], f"/ar/page/{page['route']}")
		# The title has no column: its label comes from the field name.
		self.assertEqual([field["label"] for field in item["fields"]], ["Title", "Content"])

	def test_search_finds_records_by_source_or_translation_grouped_by_resource(self):
		marker = frappe.generate_hash(length=10)
		by_source = self.make_note(f"Wrap {marker}")
		by_translation = self.make_note("Gift note")
		register("Note", by_translation.name, "title", "ar", f"هدية {marker}")

		results = translations_api.search_translations("ar", marker.upper())

		(notes,) = results
		self.assertEqual((notes["resource"], notes["label"]), ("note", "Notes"))
		self.assertEqual(
			notes["records"],
			[
				{"name": name, "title": title}
				for name, title in sorted(
					[(by_source.name, by_source.title), (by_translation.name, by_translation.title)]
				)
			],
		)
		self.assertEqual(translations_api.search_translations("ar", "  "), [])

	def test_a_commera_admin_reads_and_saves_translations(self):
		note = self.make_note("Packing note")
		add_commera_roles()
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(make_user(COMMERA_ADMIN))

		translations_api.get_overview()
		self.save({"resource": "note", "name": note.name, "field": "title", "value": "ملاحظة"})

		self.assertEqual(self.field(note, "title")["status"], CURRENT)

	def test_a_user_without_access_to_translations_is_refused(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(make_user(COMMERA_USER))

		with self.assertRaises(frappe.PermissionError):
			translations_api.get_overview()
		with self.assertRaises(frappe.PermissionError):
			translations_api.get_items("ar", "note")
		with self.assertRaises(frappe.PermissionError):
			translations_api.search_translations("ar", "note")
		with self.assertRaises(frappe.PermissionError):
			self.save({"resource": "note", "name": "x", "field": "title", "value": "x"})
