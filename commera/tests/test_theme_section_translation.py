import copy

import frappe
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.tests import IntegrationTestCase
from frappe.utils.jinja import get_jenv

from commera.api.admin import theme_layout as theme_layout_api
from commera.api.admin.theme import activate_theme
from commera.api.admin.theme_layout import discard, get_editor
from commera.localization import CURRENT, MISSING, OUTDATED, get_translatable_resource
from commera.roles import COMMERA_ADMIN, add_commera_roles
from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context, get_theme_context
from commera.shop_themes.section_text import OVERLAY, SOURCE_HASHES
from commera.shop_themes.section_translations import ThemeSectionResource
from commera.shop_themes.sections import clear_layout_cache, get_page_layout, get_text
from commera.shop_themes.theme_resolver import get_theme_environment
from commera.tests.test_admin_theme_layout import publish, save_draft
from commera.tests.test_localization import use_storefront_languages

SUMMER_THEME = "Summer Theme"
HEADING = "Beautiful Woman Purple Sweater."
ARABIC_HEADING = "سترة أرجوانية جميلة"
ENTRY = "index/hero/slide-1"
ENTRY_KEY = (ENTRY, "heading")
THEME_TRANSLATOR = "theme-translator@example.com"


class TestThemeSectionTranslation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(clear_layout_cache, SUMMER_THEME, "index")
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)

		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "page": "index"})
		clear_layout_cache(SUMMER_THEME, "index")
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		activate_theme(SUMMER_THEME)
		self.resource = get_translatable_resource("theme_section")
		self.file_layout = get_editor(SUMMER_THEME)["default_layout"]

	def editor_layout(self, heading):
		layout = copy.deepcopy(get_editor(SUMMER_THEME)["draft_layout"])
		layout["sections"][0]["blocks"][0]["settings"]["heading"] = heading
		return layout

	def entry(self, language, name=ENTRY, field="heading"):
		page = self.resource.list_entries(language, filters={"name": name, "field": field})
		return page.entries[0]

	def stored_layouts(self):
		row = frappe.db.get_value(
			"Theme Layout",
			{"theme": SUMMER_THEME, "page": "index"},
			["draft_layout", "published_layout"],
			as_dict=True,
		)
		return frappe.parse_json(row.draft_layout), frappe.parse_json(row.published_layout)

	def live_heading(self):
		layout = get_page_layout(get_theme_context(SUMMER_THEME), "index")
		return layout["sections"][0]["blocks"][0]["settings"]["heading"]

	def render_home(self, language):
		frappe.local.lang = language
		self.addCleanup(setattr, frappe.local, "lang", "en")
		environment = get_theme_environment(get_jenv(), get_render_theme_context()["dirs"])
		return environment.from_string("{{ render_layout('index') }}").render()

	def file_caption(self):
		return self.file_layout["sections"][0]["settings"]["caption"]

	def test_the_adapter_registers_through_the_hook_for_the_live_theme(self):
		self.assertIsInstance(self.resource, ThemeSectionResource)
		self.assertIsNone(self.resource.theme)
		self.assertEqual(self.resource.label, "Theme")

	def test_entries_list_each_text_setting_with_its_source_translation_and_status(self):
		publish(SUMMER_THEME, "index", self.editor_layout({"en": HEADING, "ar": ARABIC_HEADING}))

		heading = self.entry("ar")
		caption = self.entry("ar", name="index/hero", field="caption")

		self.assertEqual(
			(heading.resource, heading.source, heading.value, heading.status),
			("theme_section", HEADING, ARABIC_HEADING, CURRENT),
		)
		self.assertEqual(heading.label, "Hero slider · Slide · Heading")
		self.assertEqual((caption.source, caption.value, caption.status), (self.file_caption(), "", MISSING))
		self.assertEqual(self.entry("fr").status, MISSING)
		self.assertNotIn("url", {entry.field for entry in self.resource.iter_entries("ar")})

	def test_writing_to_an_own_layout_puts_the_translation_into_both_layouts(self):
		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))
		save_draft(SUMMER_THEME, "index", self.editor_layout(HEADING))

		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		for layout in self.stored_layouts():
			self.assertEqual(
				layout["sections"][0]["blocks"][0]["settings"]["heading"],
				{"en": HEADING, "ar": ARABIC_HEADING},
			)
		self.assertIn(ARABIC_HEADING, self.render_home("ar"))
		self.assertIn(HEADING, self.render_home("en"))

	def test_translating_an_inherited_page_stores_only_the_translation(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		draft, published = self.stored_layouts()
		self.assertIsNone(draft)
		self.assertNotIn("sections", published)
		self.assertEqual(published[OVERLAY], {"hero/slide-1": {"heading": {"ar": ARABIC_HEADING}}})
		self.assertEqual(self.live_heading(), {"en": HEADING, "ar": ARABIC_HEADING})
		self.assertIn(ARABIC_HEADING, self.render_home("ar"))
		self.assertEqual(self.entry("ar").value, ARABIC_HEADING)

	def test_the_editor_sees_overlay_translations_as_the_live_page(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		editor = get_editor(SUMMER_THEME)

		self.assertIsNone(editor["published_layout"])
		heading = editor["draft_layout"]["sections"][0]["blocks"][0]["settings"]["heading"]
		self.assertEqual(heading, {"en": HEADING, "ar": ARABIC_HEADING})
		self.assertFalse(editor["has_unpublished_changes"])

	def test_a_full_override_absorbs_the_overlay_and_keeps_it_current(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		publish(SUMMER_THEME, "index", get_editor(SUMMER_THEME)["draft_layout"])

		_draft, published = self.stored_layouts()
		self.assertNotIn(OVERLAY, published)
		heading = published["sections"][0]["blocks"][0]["settings"]["heading"]
		self.assertEqual(heading, {"en": HEADING, "ar": ARABIC_HEADING})
		self.assertEqual(self.entry("ar").status, CURRENT)

	def test_an_empty_write_to_an_untranslated_inherited_page_creates_nothing(self):
		self.resource.write(ENTRY, "heading", "ar", "")

		self.assertFalse(frappe.db.exists("Theme Layout", {"theme": SUMMER_THEME, "page": "index"}))

	def test_removing_the_only_overlay_translation_empties_the_overlay(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		self.resource.write(ENTRY, "heading", "ar", "")

		self.assertIsNone(self.stored_layouts()[1])
		self.assertEqual(self.live_heading(), HEADING)
		self.assertEqual(self.entry("ar").status, MISSING)

	def test_an_editor_opened_before_a_translation_write_cannot_save_over_it(self):
		editor = get_editor(SUMMER_THEME)
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		with self.assertRaises(frappe.TimestampMismatchError):
			theme_layout_api.save_draft(SUMMER_THEME, "index", editor["draft_layout"], editor["revision"])

		self.assertEqual(self.live_heading(), {"en": HEADING, "ar": ARABIC_HEADING})

	def test_discarding_a_draft_keeps_the_overlay_translations(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		save_draft(SUMMER_THEME, "index", self.editor_layout({"en": "ZZ Draft heading"}))

		discarded = discard(SUMMER_THEME, "index")

		heading = discarded["draft_layout"]["sections"][0]["blocks"][0]["settings"]["heading"]
		self.assertEqual(heading, {"en": HEADING, "ar": ARABIC_HEADING})
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_the_theme_editor_never_sees_the_source_hashes(self):
		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		self.assertIn(SOURCE_HASHES, self.stored_layouts()[1])
		editor = get_editor(SUMMER_THEME)
		self.assertNotIn(SOURCE_HASHES, editor["draft_layout"])
		self.assertNotIn(SOURCE_HASHES, editor["published_layout"])
		self.assertFalse(editor["has_unpublished_changes"])

	def test_writing_keeps_the_unpublished_draft_changes(self):
		layout = self.editor_layout(HEADING)
		layout["sections"][0]["settings"]["caption"] = "ZZ Draft caption"
		save_draft(SUMMER_THEME, "index", layout)

		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		draft, _published = self.stored_layouts()
		self.assertEqual(draft["sections"][0]["settings"]["caption"], "ZZ Draft caption")
		self.assertEqual(draft["sections"][0]["blocks"][0]["settings"]["heading"]["ar"], ARABIC_HEADING)
		live = get_page_layout(get_theme_context(SUMMER_THEME), "index")
		self.assertEqual(live["sections"][0]["settings"]["caption"], self.file_caption())
		self.assertEqual(self.live_heading()["ar"], ARABIC_HEADING)

	def test_a_draft_source_edit_never_makes_the_live_translation_outdated(self):
		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))
		save_draft(SUMMER_THEME, "index", self.editor_layout("ZZ Draft heading"))
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		save_draft(SUMMER_THEME, "index", get_editor(SUMMER_THEME)["draft_layout"])
		self.assertEqual(self.entry("ar").status, CURRENT)

		publish(SUMMER_THEME, "index", get_editor(SUMMER_THEME)["draft_layout"])
		published = self.entry("ar")
		self.assertEqual((published.source, published.status), ("ZZ Draft heading", CURRENT))

	def test_a_source_edit_makes_the_translation_outdated_until_it_is_rewritten(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		save_draft(SUMMER_THEME, "index", self.editor_layout({"en": "New heading", "ar": ARABIC_HEADING}))
		self.assertEqual(self.entry("ar").status, CURRENT)
		publish(SUMMER_THEME, "index", get_editor(SUMMER_THEME)["draft_layout"])

		outdated = self.entry("ar")
		self.assertEqual(
			(outdated.source, outdated.value, outdated.status), ("New heading", ARABIC_HEADING, OUTDATED)
		)
		self.assertIn(ARABIC_HEADING, self.render_home("ar"))

		self.resource.write(ENTRY, "heading", "ar", "عنوان جديد")
		self.assertEqual(self.entry("ar").status, CURRENT)

	def test_rewriting_an_unchanged_translation_marks_it_current(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		publish(SUMMER_THEME, "index", self.editor_layout({"en": "New heading", "ar": ARABIC_HEADING}))
		self.assertEqual(self.entry("ar").status, OUTDATED)

		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		self.assertEqual(self.entry("ar").status, CURRENT)

	def test_a_translation_edited_in_the_theme_editor_is_current(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		publish(SUMMER_THEME, "index", self.editor_layout({"en": "New heading", "ar": ARABIC_HEADING}))

		publish(SUMMER_THEME, "index", self.editor_layout({"en": "New heading", "ar": "عنوان جديد"}))

		self.assertEqual(self.entry("ar").status, CURRENT)

	def test_writing_an_empty_value_removes_the_translation(self):
		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		self.resource.write(ENTRY, "heading", "ar", "")

		self.assertEqual((self.entry("ar").value, self.entry("ar").status), ("", MISSING))
		self.assertNotIn("ar", self.stored_layouts()[1]["sections"][0]["blocks"][0]["settings"]["heading"])

	def test_status_counts_cover_every_section_text(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)

		counts = self.resource.count_statuses("ar")

		self.assertEqual(counts[CURRENT], 1)
		self.assertEqual(sum(counts.values()), len(list(self.resource.iter_entries("ar"))))

	def test_entries_come_in_bounded_pages(self):
		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		every = [(entry.name, entry.field) for entry in self.resource.iter_entries("ar")]

		paged, cursor = [], None
		while True:
			page = self.resource.list_entries("ar", cursor=cursor, limit=3)
			self.assertLessEqual(len(page.entries), 3)
			paged += [(entry.name, entry.field) for entry in page.entries]
			if not (cursor := page.next_cursor):
				break

		self.assertEqual(paged, every)
		self.assertEqual(
			[entry.value for entry in self.resource.list_entries("ar", status=CURRENT).entries],
			[ARABIC_HEADING],
		)
		found = self.resource.list_entries("ar", search="purple sweater").entries
		self.assertIn((ENTRY, "heading"), [(entry.name, entry.field) for entry in found])

	def test_a_page_after_an_entry_before_the_cursor_was_removed_skips_nothing(self):
		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))
		first = self.first_page_past(ENTRY_KEY)

		publish(SUMMER_THEME, "index", self.editor_layout(""))

		self.assertNotIn(ENTRY_KEY, self.keys(self.resource.iter_entries("ar")))
		self.assert_rest_follows(first)

	def test_a_page_after_an_entry_was_added_before_the_cursor_repeats_nothing(self):
		publish(SUMMER_THEME, "index", self.editor_layout(""))
		first = self.first_page_past(ENTRY_KEY)

		publish(SUMMER_THEME, "index", self.editor_layout(HEADING))

		self.assertIn(ENTRY_KEY, self.keys(self.resource.iter_entries("ar")))
		self.assert_rest_follows(first)

	def first_page_past(self, key):
		before = [entry for entry in self.keys(self.resource.iter_entries("ar")) if entry <= key]
		first = self.resource.list_entries("ar", limit=len(before) + 1)
		self.assertGreater(self.keys(first.entries)[-1], key)
		self.assertTrue(first.next_cursor)
		return first

	def assert_rest_follows(self, first):
		"""The pages after `first` hold exactly the entries after its last key now, once each."""
		rest, cursor = [], first.next_cursor
		while cursor:
			page = self.resource.list_entries("ar", cursor=cursor, limit=4)
			rest += self.keys(page.entries)
			cursor = page.next_cursor
		last = self.keys(first.entries)[-1]
		self.assertEqual(rest, [key for key in self.keys(self.resource.iter_entries("ar")) if key > last])

	def keys(self, entries):
		return [(entry.name, entry.field) for entry in entries]

	def test_a_commera_admin_translates_and_clears_theme_text(self):
		add_commera_roles()
		create_user(THEME_TRANSLATOR, COMMERA_ADMIN)
		frappe.set_user(THEME_TRANSLATOR)

		self.resource.write(ENTRY, "heading", "ar", ARABIC_HEADING)
		self.resource.write(ENTRY, "heading", "fr", "Beau pull violet.")
		self.assertEqual(self.entry("ar").value, ARABIC_HEADING)

		self.resource.write(ENTRY, "heading", "ar", "")
		self.resource.write(ENTRY, "heading", "fr", "")
		self.assertEqual((self.entry("ar").status, self.entry("fr").status), (MISSING, MISSING))
		self.assertIsNone(self.stored_layouts()[1])

	def test_only_configured_languages_other_than_the_default_take_translations(self):
		for language in ("en", "de"):
			with self.subTest(language), self.assertRaises(frappe.ValidationError):
				self.resource.write(ENTRY, "heading", language, "Text")

		self.resource.write(ENTRY, "heading", "fr", "Beau pull violet.")
		self.assertEqual(self.entry("fr").status, CURRENT)

	def test_an_unknown_entry_is_refused(self):
		for name, field in (
			(ENTRY, "url"),
			("index/hero/no-such-slide", "heading"),
			("nowhere/hero", "caption"),
		):
			with self.subTest(name), self.assertRaises(frappe.DoesNotExistError):
				self.resource.write(name, field, "ar", "Text")

	def test_a_writer_without_theme_layout_permission_is_refused(self):
		frappe.set_user("Guest")

		for value in (ARABIC_HEADING, ""):
			with self.subTest(value=value), self.assertRaises(frappe.PermissionError):
				self.resource.write(ENTRY, "heading", "ar", value)

	def test_a_layout_takes_only_storefront_language_keys(self):
		with self.assertRaisesRegex(frappe.ValidationError, "is not a storefront language"):
			save_draft(SUMMER_THEME, "index", self.editor_layout({"en": HEADING, "xx": "Text"}))

	def test_a_removed_language_never_blocks_a_save(self):
		self.resource.write(ENTRY, "heading", "fr", "Beau pull violet.")
		use_storefront_languages(self, "en", published=("en", "ar"))

		save_draft(SUMMER_THEME, "index", self.editor_layout({"en": HEADING, "fr": "Beau pull violet."}))

	def test_a_removed_language_is_kept_only_where_it_already_was(self):
		self.resource.write(ENTRY, "heading", "fr", "Beau pull violet.")
		use_storefront_languages(self, "en", published=("en", "ar"))

		layout = self.editor_layout({"en": HEADING, "fr": "Beau pull violet."})
		layout["sections"][0]["settings"]["caption"] = {"en": self.file_caption(), "fr": "Légende"}
		with self.assertRaisesRegex(frappe.ValidationError, "fr is not a storefront language"):
			save_draft(SUMMER_THEME, "index", layout)


class TestSectionTextSourceKey(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		use_storefront_languages(self, "ar", published=("ar", "en"))

	def test_the_default_language_is_the_source_of_other_languages(self):
		frappe.local.lang = "de"

		self.assertEqual(get_text({"en": "Sale", "ar": "تخفيضات"}), "تخفيضات")

	def test_legacy_english_text_is_the_source_when_the_default_has_none(self):
		frappe.local.lang = "ar"

		self.assertEqual(get_text({"en": "Sale"}), "Sale")
		self.assertEqual(get_text({"fr": "Soldes"}), "Soldes")

	def test_the_page_language_wins(self):
		frappe.local.lang = "en"

		self.assertEqual(get_text({"en": "Sale", "ar": "تخفيضات"}), "Sale")
