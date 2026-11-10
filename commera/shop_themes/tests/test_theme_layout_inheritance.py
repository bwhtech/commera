# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import copy
import csv
import io
from unittest.mock import ANY, Mock, call, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import theme_layout as theme_layout_api
from commera.api.admin.theme_layout import discard, get_editor
from commera.localization import CURRENT, OUTDATED, exchange
from commera.shop_themes import layout_cache
from commera.shop_themes.doctype.shop_theme.shop_theme import clear_theme_cache, get_theme_context
from commera.shop_themes.layout_cache import (
	clear_layout_cache,
	forget_uncommitted_layouts,
	get_cache_keys,
	has_uncommitted_layouts,
	publish_entry,
	read_published_layouts,
	set_entry,
)
from commera.shop_themes.section_text import OVERLAY, SOURCE_HASHES
from commera.shop_themes.section_translations import ThemeSectionResource
from commera.shop_themes.sections import get_inherited_layout, get_page_layout, get_theme_json
from commera.tests.test_admin_theme_layout import publish, save_draft
from commera.tests.test_localization import use_storefront_languages

PARENT = "Commera Starter"
CHILD = "ZZ Inherit Child"
GRANDCHILD = "ZZ Inherit Grandchild"
PAGE = "index"
TILE = f"{PAGE}/collections/tile-1"
OTHER_TILE = f"{PAGE}/collections/tile-2"


class TestThemeLayoutInheritance(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(clear_theme_cache)
		self.addCleanup(frappe.db.rollback)

		for theme_name, parent_theme in ((CHILD, PARENT), (GRANDCHILD, CHILD)):
			frappe.get_doc(
				doctype="Shop Theme",
				theme_name=theme_name,
				theme_type="Sections",
				parent_theme=parent_theme,
				module="Shop Themes",
			).db_insert()
		clear_theme_cache()

		frappe.db.delete("Theme Layout", {"theme": PARENT, "page": PAGE})
		for theme_name in (PARENT, CHILD, GRANDCHILD):
			clear_layout_cache(theme_name, PAGE)
			self.addCleanup(clear_layout_cache, theme_name, PAGE)

		self.file_layout = get_theme_json(get_theme_context(PARENT)["dirs"], f"layouts/{PAGE}.json")

	def reordered_layout(self, shift):
		sections = self.file_layout["sections"]
		return {**self.file_layout, "sections": sections[shift:] + sections[:shift]}

	def rendered_layout(self, theme_name):
		return get_page_layout(get_theme_context(theme_name), PAGE)

	def test_a_child_renders_its_parents_published_layout(self):
		self.assertEqual(self.rendered_layout(CHILD), self.file_layout)

		publish(PARENT, PAGE, self.reordered_layout(1))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

	def test_a_childs_own_published_layout_wins(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		publish(CHILD, PAGE, self.reordered_layout(2))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(PARENT), self.reordered_layout(1))

	def test_a_grandchild_inherits_the_nearest_published_ancestor(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(GRANDCHILD), self.reordered_layout(1))

		publish(CHILD, PAGE, self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(GRANDCHILD), self.reordered_layout(2))

	def test_a_parent_publishing_again_reaches_a_child_already_cached(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

		publish(PARENT, PAGE, self.reordered_layout(3))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(3))

	def test_the_editor_opens_an_unedited_child_page_on_the_parents_layout(self):
		publish(PARENT, PAGE, self.reordered_layout(1))

		editor = get_editor(CHILD, PAGE)

		self.assertIsNone(editor["published_layout"])
		self.assertEqual(editor["default_layout"], self.reordered_layout(1))
		self.assertEqual(editor["draft_layout"], self.reordered_layout(1))
		self.assertFalse(editor["has_unpublished_changes"])

		save_draft(CHILD, PAGE, self.reordered_layout(2))
		discarded = discard(CHILD, PAGE)

		self.assertEqual(discarded["draft_layout"], self.reordered_layout(1))
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_a_translated_inherited_page_still_follows_its_parent(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		translatable(CHILD).write(TILE, "title", "ar", "نساء")

		publish(PARENT, PAGE, self.reordered_layout(1))

		layout = self.rendered_layout(CHILD)
		self.assertEqual([section["id"] for section in layout["sections"]], self.section_ids(1))
		tiles = next(section for section in layout["sections"] if section["id"] == "collections")
		self.assertEqual(tiles["blocks"][0]["settings"]["title"], {"en": "Women", "ar": "نساء"})
		self.assertEqual(self.rendered_layout(PARENT), self.reordered_layout(1))

	def section_ids(self, shift):
		return [section["id"] for section in self.reordered_layout(shift)["sections"]]

	def test_a_child_page_opened_before_its_parent_changed_cannot_be_saved(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		parent = translatable(PARENT)
		parent.write(TILE, "title", "ar", "نساء")
		editor = get_editor(CHILD, PAGE)

		parent.write(TILE, "title", "ar", "سيدات")

		for endpoint in (theme_layout_api.save_draft, theme_layout_api.publish):
			with self.subTest(endpoint.__name__), self.assertRaises(frappe.TimestampMismatchError):
				endpoint(CHILD, PAGE, editor["draft_layout"], editor["revision"])
		fresh = get_editor(CHILD, PAGE)
		theme_layout_api.publish(CHILD, PAGE, fresh["draft_layout"], fresh["revision"])
		self.assertEqual(self.tile_title(CHILD), {"en": "Women", "ar": "سيدات"})

	def test_a_grandchild_page_sees_a_change_two_themes_up(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		editor = get_editor(GRANDCHILD, PAGE)

		publish(PARENT, PAGE, self.reordered_layout(1))

		with self.assertRaises(frappe.TimestampMismatchError):
			theme_layout_api.save_draft(GRANDCHILD, PAGE, editor["draft_layout"], editor["revision"])

	def test_a_translation_of_a_block_the_parent_removed_never_blocks_a_save(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		child = translatable(CHILD)
		child.write(TILE, "title", "fr", "Femmes")
		use_storefront_languages(self, "en", published=("en", "ar"))
		publish(PARENT, PAGE, self.edited_tiles(lambda tiles: tiles.pop(0)))

		child.write(OTHER_TILE, "title", "ar", "رجال")

		overlay = self.child_overlay()
		self.assertEqual(overlay[OVERLAY]["collections/tile-1"], {"title": {"fr": "Femmes"}})
		self.assertEqual(overlay[OVERLAY]["collections/tile-2"], {"title": {"ar": "رجال"}})
		self.assertCountEqual(overlay[SOURCE_HASHES], ["collections/tile-1", "collections/tile-2"])

	def test_a_translation_comes_back_when_the_parent_restores_its_block(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		child = translatable(CHILD)
		child.write(TILE, "title", "ar", "نساء")
		publish(PARENT, PAGE, self.edited_tiles(lambda tiles: tiles.pop(0)))
		child.write(OTHER_TILE, "title", "ar", "رجال")
		self.assertEqual(self.title_entries(child), [])

		publish(PARENT, PAGE, self.file_layout)

		self.assertEqual(self.tile_title(CHILD), {"en": "Women", "ar": "نساء"})
		[entry] = self.title_entries(child)
		self.assertEqual((entry.value, entry.status), ("نساء", CURRENT))

	def title_entries(self, resource):
		return resource.list_entries("ar", filters={"name": TILE, "field": "title"}).entries

	def commit_layouts(self, queued=0):
		"""Run the layout callbacks a commit would run; the test transaction stays open."""
		for callback in list(frappe.db.after_commit._functions)[queued:]:
			if getattr(callback, "func", None) is publish_entry or callback is forget_uncommitted_layouts:
				callback()

	def cached_entry(self, theme_name):
		return frappe.cache.get_value(get_cache_keys([theme_name], PAGE)[0], use_local_cache=False)

	def test_the_editor_reads_the_parent_layout_past_a_stale_cache(self):
		queued = len(frappe.db.after_commit)
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.commit_layouts(queued)
		set_entry(get_cache_keys([PARENT], PAGE)[0], {"layout": self.reordered_layout(2)})

		editor = get_editor(CHILD, PAGE)

		self.assertEqual(editor["default_layout"], self.reordered_layout(1))
		self.assertEqual(editor["draft_layout"], self.reordered_layout(1))
		theme_layout_api.save_draft(CHILD, PAGE, editor["draft_layout"], editor["revision"])

	def test_a_commit_caches_the_committed_layout(self):
		queued = len(frappe.db.after_commit)
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertTrue(has_uncommitted_layouts())

		self.commit_layouts(queued)

		self.assertFalse(has_uncommitted_layouts())
		self.assertEqual(self.cached_entry(PARENT), {"layout": self.reordered_layout(1)})
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

	def test_a_reader_that_read_the_old_row_before_a_commit_cannot_cache_it(self):
		queued = len(frappe.db.after_commit)
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.commit_layouts(queued)
		clear_layout_cache(PARENT, PAGE)
		reads = []

		def read_then_let_a_writer_commit(theme_names, page):
			stored = read_published_layouts(theme_names, page)
			if not reads:
				reads.append(page)
				queued = len(frappe.db.after_commit)
				publish(PARENT, PAGE, self.reordered_layout(2))
				self.commit_layouts(queued)
			return stored

		with patch.object(layout_cache, "read_published_layouts", read_then_let_a_writer_commit):
			# The stale reader still sees the old row it read, and caches it under the old generation.
			self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

	def test_a_reader_on_an_older_snapshot_cannot_replace_the_committed_layout(self):
		queued = len(frappe.db.after_commit)
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.commit_layouts(queued)
		old_rows = read_published_layouts([CHILD, PARENT], PAGE)
		queued = len(frappe.db.after_commit)
		publish(PARENT, PAGE, self.reordered_layout(2))
		self.commit_layouts(queued)

		# It reads the new generation, but its snapshot predates the commit.
		with patch.object(layout_cache, "read_published_layouts", return_value=old_rows):
			self.rendered_layout(CHILD)

		self.assertEqual(self.cached_entry(PARENT), {"layout": self.reordered_layout(2)})
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

	def test_a_rolled_back_layout_leaves_nothing_cached(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(PARENT), self.reordered_layout(1))
		self.assertIsNone(self.cached_entry(PARENT))

		frappe.db.rollback()

		self.assertFalse(has_uncommitted_layouts())
		self.assertIsNone(self.cached_entry(PARENT))
		committed = get_inherited_layout([PARENT], get_theme_context(PARENT)["dirs"], PAGE, cached=False)
		self.assertEqual(self.rendered_layout(PARENT), committed)
		self.assertEqual(
			self.cached_entry(PARENT), {"layout": read_published_layouts([PARENT], PAGE)[PARENT]}
		)

	def test_a_save_locks_the_page_and_its_parents_in_one_ordered_read(self):
		theme_context = get_theme_context(GRANDCHILD)
		query = str(theme_layout_api.get_layout_rows_query(theme_context, PAGE, lock=True))

		for theme_name in (GRANDCHILD, CHILD, PARENT):
			self.assertIn(f"'{theme_name}'", query)
		self.assertTrue(query.endswith("ORDER BY `name` FOR UPDATE"), query)

		reads = Mock(wraps=theme_layout_api.read_layout_rows)
		with patch.object(theme_layout_api, "read_layout_rows", reads):
			save_draft(GRANDCHILD, PAGE, self.reordered_layout(1))
		self.assertIn(call(ANY, PAGE, lock=True), reads.call_args_list)

	def test_a_translation_of_a_block_the_parent_removed_can_be_cleared(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		child = translatable(CHILD)
		child.write(TILE, "title", "ar", "نساء")
		publish(PARENT, PAGE, self.edited_tiles(lambda tiles: tiles.pop(0)))

		child.write(TILE, "title", "ar", "")

		self.assertIsNone(self.child_overlay())
		with self.assertRaises(frappe.DoesNotExistError):
			child.write(TILE, "title", "ar", "نساء")

	def test_a_dormant_overlay_translation_is_still_exchanged(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		child = translatable(CHILD)
		child.write(TILE, "title", "ar", "نساء")
		child.write(OTHER_TILE, "title", "ar", "رجال")
		publish(PARENT, PAGE, self.edited_tiles(lambda tiles: tiles[0]["settings"].update(title="")))
		before = self.child_overlay()

		with patch.object(exchange, "get_translatable_resources", return_value=[child]):
			content = exchange.export_csv("ar")
			report = exchange.import_csv(content, "ar")

		rows = {(row["Identification"], row["Field"]): row for row in csv.DictReader(io.StringIO(content))}
		dormant = rows[(TILE, "title")]
		self.assertEqual(
			(dormant["Status"], dormant["Default content"], dormant["Translated content"]),
			(OUTDATED, "", "نساء"),
		)
		self.assertEqual(rows[(OTHER_TILE, "title")]["Status"], CURRENT)
		self.assertEqual(self.title_entries(child), [])
		self.assertEqual((report.updated, report.errors), (0, []))
		self.assertEqual(self.child_overlay(), before)

	def test_an_unchanged_stored_translation_never_blocks_a_save(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		child = translatable(CHILD)
		child.write(TILE, "title", "fr", "Femmes")
		use_storefront_languages(self, "en", published=("en", "ar"))
		# The setting stays, but without a source the removed French key is no longer held anywhere.
		publish(PARENT, PAGE, self.edited_tiles(lambda tiles: tiles[0]["settings"].update(title="")))

		child.write(OTHER_TILE, "title", "ar", "رجال")

		self.assertEqual(self.child_overlay()[OVERLAY]["collections/tile-1"], {"title": {"fr": "Femmes"}})

	def edited_tiles(self, edit):
		layout = copy.deepcopy(self.file_layout)
		edit(next(section for section in layout["sections"] if section["id"] == "collections")["blocks"])
		return layout

	def tile_title(self, theme_name):
		tiles = next(
			section
			for section in self.rendered_layout(theme_name)["sections"]
			if section["id"] == "collections"
		)
		return tiles["blocks"][0]["settings"]["title"]

	def child_overlay(self):
		layout = frappe.db.get_value("Theme Layout", {"theme": CHILD, "page": PAGE}, "published_layout")
		return frappe.parse_json(layout) if layout else None


def translatable(theme_name):
	return ThemeSectionResource(type="theme_section", label="Theme", theme=theme_name)
