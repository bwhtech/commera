import copy
import re
import shutil
import tempfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from commera.patches import move_summer_home_into_theme_layout as summer_home_patch
from commera.shop_themes.doctype.shop_theme.shop_theme import THEME_CONTEXT_CACHE_KEY, get_theme_context
from commera.shop_themes.doctype.theme_layout.theme_layout import (
	LAYOUT_CACHE_KEY,
	get_saved_layout,
	save_theme_layout,
)
from commera.shop_themes.section_render import ERROR_THROTTLE_CACHE_PREFIX
from commera.shop_themes.summer_layout import (
	SUMMER_SETTINGS_DOCTYPE,
	SUMMER_THEME,
	build_summer_index_layout,
	get_summer_layout_themes,
)
from commera.shop_themes.tests.theme_fixtures import write_theme_files
from commera.shop_themes.theme_files import get_default_layout, read_theme_json, theme_file_cache
from commera.utils import get_product_list

SECTION_TYPE_PATTERN = re.compile(r'data-section-type="([a-z_]+)"')
SETTINGS_DRIVEN_SECTIONS = (
	"hero_slider",
	"category_strip",
	"products_grid",
	"collection",
	"everyday_essentials",
	"deals",
	"offers",
	"featured",
)
CHILD_THEME = "Summer Fixture Child"


class IntegrationTestSummerLayout(IntegrationTestCase):
	def setUp(self):
		self.original_active_theme = frappe.db.get_single_value("Shop Theme Settings", "active_theme")
		self.original_lang = frappe.local.lang
		self.addCleanup(self.restore_site)
		self.clear_theme_caches()
		self.variants = frappe.get_all(
			"Style Attribute Variant", filters={"is_published": 1}, order_by="name asc", pluck="name", limit=6
		)
		if len(self.variants) < 6:
			self.skipTest("needs six published variants")

	def restore_site(self):
		frappe.db.rollback()
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", self.original_active_theme)
		frappe.local.lang = self.original_lang
		self.clear_theme_caches()

	def clear_theme_caches(self):
		frappe.clear_cache()
		frappe.clear_document_cache(SUMMER_SETTINGS_DOCTYPE, SUMMER_SETTINGS_DOCTYPE)
		theme_file_cache.clear()
		frappe.cache.delete_value(LAYOUT_CACHE_KEY)
		frappe.cache.delete_keys(f"{ERROR_THROTTLE_CACHE_PREFIX}|{SUMMER_THEME}")

	def get_empty_settings(self):
		return frappe.new_doc(SUMMER_SETTINGS_DOCTYPE)

	def get_seeded_settings(self):
		settings = self.get_empty_settings()
		settings.products_title = "Picked for you"
		settings.deals_title = "Hot & cheap"
		for position in (1, 2):
			settings.append(
				"hero_slides",
				{
					"image": f"/files/slide-{position}.png",
					"heading": f"Slide {position}",
					"cta_label": "Shop",
				},
			)
			settings.append(
				"collection_banners", {"image": f"/files/banner-{position}.png", "heading": "Edit"}
			)
			settings.append("offer_banners", {"image": f"/files/offer-{position}.png", "heading": "Offer"})
		for position in range(1, 7):
			settings.append(
				"shop_by_category", {"image": f"/files/category-{position}.png", "heading": f"C{position}"}
			)
		for variant in reversed(self.variants):
			settings.append("best_picks", {"item_variant": variant})
		settings.append("best_picks", {"item_variant": self.variants[0]})
		settings.append("deal_picks", {"item_variant": self.variants[1]})
		settings.append("featured_picks", {"item_variant": self.variants[2]})
		return settings

	def get_section(self, layout, section_type):
		return next(section for section in layout["sections"] if section["type"] == section_type)

	def add_summer_child(self, files):
		summer_context = get_theme_context(SUMMER_THEME)
		child_dir = tempfile.mkdtemp(prefix="commera_summer_child_")
		self.addCleanup(shutil.rmtree, child_dir)
		write_theme_files(child_dir, files)

		developer_mode = frappe.conf.developer_mode
		frappe.conf.developer_mode = 0
		try:
			frappe.new_doc(
				"Shop Theme",
				theme_name=CHILD_THEME,
				module="Shop Themes",
				parent_theme=SUMMER_THEME,
				theme_settings=SUMMER_SETTINGS_DOCTYPE,
			).insert()
		finally:
			frappe.conf.developer_mode = developer_mode

		child_context = {
			**summer_context,
			"theme_name": CHILD_THEME,
			"names": [CHILD_THEME, *summer_context["names"]],
			"dirs": [child_dir, *summer_context["dirs"]],
		}
		frappe.cache.hset(THEME_CONTEXT_CACHE_KEY, CHILD_THEME, child_context)
		self.addCleanup(frappe.cache.hdel, THEME_CONTEXT_CACHE_KEY, CHILD_THEME)
		return child_context["dirs"]

	def get_summer_schema(self, section_type):
		return copy.deepcopy(
			read_theme_json(get_theme_context(SUMMER_THEME)["dirs"], f"sections/{section_type}.json")
		)

	def assert_saved_layout(self, expected, theme=SUMMER_THEME):
		saved = get_saved_layout(theme, "index")
		self.assertEqual(get_outline(saved), get_outline(expected))
		for saved_section, section in zip(saved["sections"], expected["sections"], strict=True):
			self.assert_settings_kept(saved_section, section)
			for saved_block, block in zip(saved_section["blocks"], section.get("blocks") or [], strict=True):
				self.assert_settings_kept(saved_block, block)

	def assert_settings_kept(self, saved, expected):
		settings = expected.get("settings") or {}
		self.assertEqual({key: saved["settings"].get(key) for key in settings}, settings)

	def get_home(self, lang="en"):
		frappe.local.lang = lang
		for local_key in ("jenv", "jenv_restricted", "jenv_unrestricted"):
			if hasattr(frappe.local, local_key):
				delattr(frappe.local, local_key)
		set_request(method="GET", path=f"/{lang}")
		response = get_response()
		self.assertEqual(response.status_code, 200)
		return frappe.safe_decode(response.get_data())

	def test_layout_maps_settings_rows_into_blocks(self):
		layout = build_summer_index_layout(self.get_seeded_settings())

		hero = self.get_section(layout, "hero_slider")
		self.assertEqual([block["id"] for block in hero["blocks"]], ["slide-1", "slide-2"])
		self.assertEqual(hero["blocks"][0]["type"], "slide")
		self.assertEqual(hero["blocks"][0]["settings"]["heading"], "Slide 1")
		self.assertEqual(hero["blocks"][0]["settings"]["subheading"], "")
		self.assertEqual(hero["settings"]["caption_label"], "Summer Collection")

		offers = self.get_section(layout, "offers")
		self.assertEqual([block["id"] for block in offers["blocks"]], ["offer-1", "offer-2"])
		self.assertEqual({block["type"] for block in offers["blocks"]}, {"banner"})
		self.assertEqual(self.get_section(layout, "deals")["settings"]["heading"], "Hot & cheap")
		self.assertEqual(self.get_section(layout, "deals")["settings"]["link_url"], "")

		collage = self.get_section(layout, "collection_collage")["settings"]
		self.assertEqual(
			[collage[f"image_{slot}"] for slot in range(1, 6)],
			[f"/files/category-{position}.png" for position in range(1, 6)],
		)
		self.assertEqual(len(self.get_section(layout, "category_strip")["blocks"]), 6)

	def test_picks_are_unique_in_name_order_and_capped(self):
		settings = self.get_seeded_settings()
		settings.append("best_picks", {"item_variant": "No Such Variant"})

		layout = build_summer_index_layout(settings)

		grid_picks = [
			block["settings"]["product"] for block in self.get_section(layout, "products_grid")["blocks"]
		]
		self.assertEqual(grid_picks, self.variants)
		essentials = self.get_section(layout, "everyday_essentials")["blocks"]
		self.assertEqual([block["settings"]["product"] for block in essentials], self.variants[:4])
		self.assertEqual([block["id"] for block in essentials], [f"ee-pick-{n}" for n in range(1, 5)])
		self.assertEqual(
			[block["id"] for block in self.get_section(layout, "deals")["blocks"]], ["deal-pick-1"]
		)

	def test_empty_settings_give_the_default_layout(self):
		self.assertEqual(
			build_summer_index_layout(self.get_empty_settings()),
			get_default_layout(get_theme_context(SUMMER_THEME)["dirs"], "index"),
		)

	def test_patch_creates_each_row_once(self):
		frappe.db.delete("Theme Layout", {"template": "index", "theme": ["in", get_summer_layout_themes()]})
		settings = frappe.get_single(SUMMER_SETTINGS_DOCTYPE)

		summer_home_patch.execute()
		summer_home_patch.execute()

		for theme in get_summer_layout_themes():
			with self.subTest(theme=theme):
				expected = build_summer_index_layout(settings, theme)
				filters = {"theme": theme, "template": "index"}
				self.assertEqual(frappe.db.count("Theme Layout", filters), 1)
				self.assert_saved_layout(expected, theme)
				self.assertEqual(frappe.db.get_value("Theme Layout", filters, "is_synced_from_settings"), 1)

	def test_patch_logs_a_theme_whose_layout_is_invalid_and_moves_the_others(self):
		if not frappe.get_single(SUMMER_SETTINGS_DOCTYPE).best_picks:
			self.skipTest("needs best picks in Summer Theme Settings")
		products_grid = self.get_summer_schema("products_grid")
		products_grid["blocks"]["pick"]["settings"][0]["type"] = "collection"
		self.add_summer_child({"sections/products_grid.json": products_grid})
		frappe.db.delete("Theme Layout", {"template": "index", "theme": ["in", get_summer_layout_themes()]})
		started_at = frappe.utils.now_datetime()

		summer_home_patch.execute()

		self.assertIsNone(get_saved_layout(CHILD_THEME, "index"))
		self.assertIsNotNone(get_saved_layout(SUMMER_THEME, "index"))
		error_logs = frappe.get_all(
			"Error Log",
			filters={"reference_name": CHILD_THEME, "creation": [">=", started_at]},
			pluck="method",
		)
		self.assertEqual(error_logs, ["Summer home could not move into Theme Layout"])

	def test_patch_leaves_an_existing_row_alone(self):
		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "template": "index"})
		edited = {"sections": [{"id": "marquee", "type": "marquee"}]}
		save_theme_layout(SUMMER_THEME, "index", edited)

		summer_home_patch.execute()

		self.assert_saved_layout(edited)

	def test_saving_settings_rewrites_the_layout(self):
		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "template": "index"})
		settings = frappe.get_doc(SUMMER_SETTINGS_DOCTYPE)
		settings.save()
		settings.products_title = "Fresh this week"
		settings.save()

		saved = get_saved_layout(SUMMER_THEME, "index")
		self.assertEqual(self.get_section(saved, "products_grid")["settings"]["heading"], "Fresh this week")

	def test_saving_settings_leaves_an_edited_layout_alone(self):
		settings = frappe.get_doc(SUMMER_SETTINGS_DOCTYPE)
		settings.save()
		edited = build_summer_index_layout(settings)
		edited["sections"].reverse()
		save_theme_layout(SUMMER_THEME, "index", edited)

		settings.products_title = "Fresh this week"
		settings.save()

		self.assert_saved_layout(edited)

	def test_saving_settings_still_syncs_after_the_default_layout_file_changed(self):
		settings = frappe.get_doc(SUMMER_SETTINGS_DOCTYPE)
		from_older_release = build_summer_index_layout(settings)
		from_older_release["sections"].reverse()
		save_theme_layout(SUMMER_THEME, "index", from_older_release, synced_from_settings=True)

		settings.products_title = "Fresh this week"
		settings.save()

		self.assert_saved_layout(build_summer_index_layout(settings))

	def test_any_other_save_takes_the_row_away_from_the_settings(self):
		filters = {"theme": SUMMER_THEME, "template": "index"}
		layout = build_summer_index_layout(frappe.get_doc(SUMMER_SETTINGS_DOCTYPE))
		save_theme_layout(SUMMER_THEME, "index", layout, synced_from_settings=True)
		self.assertEqual(frappe.db.get_value("Theme Layout", filters, "is_synced_from_settings"), 1)

		save_theme_layout(SUMMER_THEME, "index", layout)

		self.assertEqual(frappe.db.get_value("Theme Layout", filters, "is_synced_from_settings"), 0)

	def test_a_user_without_theme_layout_access_can_save_the_settings(self):
		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "template": "index"})
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")
		self.assertFalse(frappe.has_permission("Theme Layout", "write"))

		frappe.get_doc(SUMMER_SETTINGS_DOCTYPE).save(ignore_permissions=True)

		self.assertIsNotNone(get_saved_layout(SUMMER_THEME, "index"))

	def test_a_child_theme_gets_a_layout_from_its_own_files(self):
		deals = self.get_summer_schema("deals")
		deals["settings"] = [setting for setting in deals["settings"] if setting["id"] != "link_label"]
		summer_index = get_default_layout(get_theme_context(SUMMER_THEME)["dirs"], "index")
		child_index = {
			"sections": [
				section for section in summer_index["sections"] if section["type"] in ("deals", "offers")
			]
		}
		for section in child_index["sections"]:
			section["settings"].pop("link_label", None)
		self.add_summer_child({"sections/deals.json": deals, "layouts/index.json": child_index})
		frappe.db.delete("Theme Layout", {"template": "index", "theme": ["in", get_summer_layout_themes()]})

		settings = frappe.get_doc(SUMMER_SETTINGS_DOCTYPE)
		settings.deals_title = "Hot & cheap"
		settings.deals_link_label = "All deals"
		settings.save()

		child_layout = get_saved_layout(CHILD_THEME, "index")
		self.assertEqual([section["type"] for section in child_layout["sections"]], ["deals", "offers"])
		self.assertEqual(
			self.get_section(child_layout, "deals")["settings"], {"heading": "Hot & cheap", "link_url": ""}
		)
		summer_deals = self.get_section(get_saved_layout(SUMMER_THEME, "index"), "deals")
		self.assertEqual(summer_deals["settings"]["link_label"], "All deals")

	def test_saving_settings_creates_a_missing_row(self):
		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "template": "index"})

		frappe.get_doc(SUMMER_SETTINGS_DOCTYPE).save()

		self.assertIsNotNone(get_saved_layout(SUMMER_THEME, "index"))

	def test_home_shows_a_section_for_each_seeded_setting(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", SUMMER_THEME)
		frappe.clear_cache()

		save_theme_layout(SUMMER_THEME, "index", build_summer_index_layout(self.get_seeded_settings()))
		html = self.get_home()
		arabic_html = self.get_home("ar")

		for section_type in SETTINGS_DRIVEN_SECTIONS:
			with self.subTest(section_type=section_type):
				self.assertIn(f'data-section-type="{section_type}"', html)
		self.assertIn("Hot &amp; cheap", html)
		self.assertIn('data-section-type="hero_slider"', arabic_html)
		self.assertNotIn("{{", html)

	def test_home_fetches_the_picked_products_once(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", SUMMER_THEME)
		frappe.clear_cache()

		save_theme_layout(SUMMER_THEME, "index", build_summer_index_layout(self.get_seeded_settings()))
		with patch("commera.shop_themes.section_data.get_product_list", wraps=get_product_list) as fetch:
			self.get_home()

		self.assertEqual(fetch.call_count, 1)

	def test_home_hides_sections_with_nothing_to_show(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", SUMMER_THEME)
		frappe.clear_cache()

		save_theme_layout(SUMMER_THEME, "index", build_summer_index_layout(self.get_empty_settings()))
		rendered_types = SECTION_TYPE_PATTERN.findall(self.get_home())

		self.assertFalse(set(rendered_types) & set(SETTINGS_DRIVEN_SECTIONS))


def get_outline(layout):
	return [
		(
			section["id"],
			section["type"],
			[(block["id"], block["type"]) for block in section.get("blocks") or []],
		)
		for section in layout["sections"]
	]
