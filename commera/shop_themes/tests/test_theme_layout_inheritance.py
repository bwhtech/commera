# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import copy
import csv
import io
from contextlib import contextmanager
from unittest.mock import ANY, Mock, call, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import theme_layout as theme_layout_api
from commera.api.admin.theme_layout import discard, get_editor
from commera.localization import CURRENT, OUTDATED, exchange
from commera.shop_themes import layout_cache
from commera.shop_themes.doctype.shop_theme.shop_theme import clear_theme_cache, get_theme_context
from commera.shop_themes.section_text import OVERLAY, SOURCE_HASHES
from commera.shop_themes.section_translations import ThemeSectionResource
from commera.shop_themes.sections import get_page_layout, get_theme_json
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

	def snapshot(self):
		"""The parent's rows as a reader on this snapshot sees them."""
		return layout_cache.read_rows(
			[CHILD, PARENT], PAGE, ["name", "modified", "theme", "published_layout"]
		)

	@contextmanager
	def reading(self, snapshot):
		"""Serve the cache's reads from an older snapshot, as a concurrent reader would."""

		def read_rows(theme_names, page, fields):
			return [frappe._dict({field: row[field] for field in fields}) for row in snapshot]

		with patch.object(layout_cache, "read_rows", read_rows):
			yield

	def cached_layouts(self, snapshot):
		key = layout_cache.get_cache_key([CHILD, PARENT], PAGE, snapshot)
		return frappe.cache.get_value(key, use_local_cache=False)

	def test_a_read_after_each_save_sees_the_saved_layout(self):
		for shift in (1, 2, 3, 1):
			publish(PARENT, PAGE, self.reordered_layout(shift))
			self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(shift))
			self.assertEqual(self.rendered_layout(PARENT), self.reordered_layout(shift))

	def test_a_reader_on_an_older_snapshot_caches_only_under_its_own_version(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		old = self.snapshot()
		publish(PARENT, PAGE, self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

		with self.reading(old):
			self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

		self.assertEqual(self.cached_layouts(old)[PARENT], self.reordered_layout(1))
		self.assertEqual(self.cached_layouts(self.snapshot())[PARENT], self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

	def test_writers_caching_out_of_commit_order_cannot_serve_the_older_layout(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		first = self.snapshot()
		publish(PARENT, PAGE, self.reordered_layout(2))
		second = self.snapshot()

		with self.reading(second):
			self.rendered_layout(CHILD)
		with self.reading(first):
			self.rendered_layout(CHILD)

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

	def test_an_evicted_entry_is_read_again(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))
		key = layout_cache.get_cache_key([CHILD, PARENT], PAGE, self.snapshot())
		frappe.cache.delete_value(key)

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))
		self.assertEqual(self.cached_layouts(self.snapshot())[PARENT], self.reordered_layout(1))

	def test_a_layout_rolled_back_to_a_savepoint_is_not_served(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		frappe.db.savepoint("layout_cache_test")
		publish(PARENT, PAGE, self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))

		frappe.db.rollback(save_point="layout_cache_test")

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))
		publish(PARENT, PAGE, self.reordered_layout(3))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(3))

	def test_a_deleted_layout_falls_back_to_the_theme_file(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

		frappe.delete_doc("Theme Layout", f"{PARENT}-{PAGE}")

		self.assertEqual(self.rendered_layout(CHILD), self.file_layout)

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
