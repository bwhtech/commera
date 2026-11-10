# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import base64
import copy
import io

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.jinja import get_jenv
from PIL import Image

from commera.api.admin import theme_layout as theme_layout_api
from commera.api.admin.theme import activate_theme
from commera.api.admin.theme_layout import discard, get_editor, save_thumbnail
from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context
from commera.shop_themes.sections import clear_layout_cache
from commera.shop_themes.theme_resolver import get_theme_environment

SUMMER_THEME = "Summer Theme"
CLASSIC_THEME = "Shop Default Theme"


def current_revision(theme, page):
	return get_editor(theme, page)["revision"]


def save_draft(theme, page, layout):
	"""The editor's save, made over the page as it is stored now."""
	return theme_layout_api.save_draft(theme, page, layout, current_revision(theme, page))


def publish(theme, page, layout):
	return theme_layout_api.publish(theme, page, layout, current_revision(theme, page))


def image_data_url(image_format, color="red"):
	buffer = io.BytesIO()
	Image.new("RGB", (8, 5), color).save(buffer, format=image_format)
	return f"data:image/{image_format.lower()};base64,{base64.b64encode(buffer.getvalue()).decode()}"


class TestAdminThemeLayout(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(clear_layout_cache, SUMMER_THEME, "index")
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "page": "index"})
		clear_layout_cache(SUMMER_THEME, "index")
		self.file_layout = get_editor(SUMMER_THEME)["default_layout"]

	def edited_layout(self, heading):
		layout = copy.deepcopy(self.file_layout)
		layout["sections"][0]["blocks"][0]["settings"]["heading"] = heading
		return layout

	def render_home_layout(self):
		activate_theme(SUMMER_THEME)
		theme_environment = get_theme_environment(get_jenv(), get_render_theme_context()["dirs"])
		return theme_environment.from_string("{{ render_layout('index') }}").render()

	def test_get_editor_says_whether_the_theme_is_live(self):
		activate_theme(SUMMER_THEME)
		self.assertTrue(get_editor(SUMMER_THEME)["live"])

		activate_theme(CLASSIC_THEME)
		self.assertFalse(get_editor(SUMMER_THEME)["live"])

	def test_get_editor_opens_the_theme_file_layout_when_nothing_is_saved(self):
		editor = get_editor(SUMMER_THEME, "index")

		self.assertEqual(editor["theme_type"], "Sections")
		self.assertIn("index", editor["pages"])
		self.assertIsNone(editor["published_layout"])
		self.assertFalse(editor["has_unpublished_changes"])
		self.assertEqual(editor["draft_layout"], editor["default_layout"])
		self.assertEqual(editor["settings"]["doctype"], "Summer Theme Settings")

		schemas = {schema["type"]: schema for schema in editor["section_schemas"]}
		self.assertEqual(schemas["hero_slider"]["category"], "Banners")
		self.assertIn("slide", schemas["hero_slider"]["blocks"])
		for section in editor["default_layout"]["sections"]:
			self.assertIn(section["type"], schemas)

	def test_save_draft_round_trips_without_touching_the_live_layout(self):
		layout = self.edited_layout("ZZ Draft Heading")

		saved = save_draft(SUMMER_THEME, "index", frappe.as_json(layout))

		self.assertEqual(saved["draft_layout"], layout)
		self.assertIsNone(saved["published_layout"])
		self.assertTrue(saved["has_unpublished_changes"])
		self.assertEqual(get_editor(SUMMER_THEME)["draft_layout"], layout)
		self.assertNotIn("ZZ Draft Heading", self.render_home_layout())

	def test_save_draft_refuses_a_layout_the_theme_cannot_render(self):
		layout = copy.deepcopy(self.file_layout)
		layout["sections"].append({"id": "zz-ghost", "type": "no_such_section"})

		self.assertRaises(frappe.ValidationError, save_draft, SUMMER_THEME, "index", layout)
		self.assertFalse(frappe.db.exists("Theme Layout", {"theme": SUMMER_THEME, "page": "index"}))

	def test_publish_changes_what_the_storefront_renders(self):
		layout = self.edited_layout("ZZ Published Heading")

		published = publish(SUMMER_THEME, "index", layout)

		self.assertEqual(published["published_layout"], layout)
		self.assertFalse(published["has_unpublished_changes"])
		self.assertIn("ZZ Published Heading", self.render_home_layout())

	def test_discard_restores_the_published_layout(self):
		published_layout = self.edited_layout("ZZ Published Heading")
		publish(SUMMER_THEME, "index", published_layout)
		save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Draft Heading"))

		discarded = discard(SUMMER_THEME, "index")

		self.assertEqual(discarded["draft_layout"], published_layout)
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_discard_restores_the_theme_file_layout_when_never_published(self):
		save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Draft Heading"))

		discarded = discard(SUMMER_THEME, "index")

		self.assertEqual(discarded["draft_layout"], self.file_layout)
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_a_classic_theme_has_no_layouts_to_edit(self):
		self.assertRaises(frappe.ValidationError, get_editor, CLASSIC_THEME)
		self.assertRaises(frappe.ValidationError, save_draft, CLASSIC_THEME, "index", self.file_layout)

	def test_a_page_the_theme_ships_no_layout_for_is_refused(self):
		self.assertRaises(frappe.ValidationError, get_editor, SUMMER_THEME, "zz-no-such-page")

	def test_only_store_managers_reach_the_editor(self):
		frappe.set_user("Guest")

		self.assertRaises(frappe.PermissionError, get_editor, SUMMER_THEME)
		self.assertRaises(frappe.PermissionError, save_draft, SUMMER_THEME, "index", self.file_layout)
		self.assertRaises(frappe.PermissionError, publish, SUMMER_THEME, "index", self.file_layout)
		self.assertRaises(frappe.PermissionError, discard, SUMMER_THEME, "index")
		self.assertRaises(frappe.PermissionError, save_thumbnail, SUMMER_THEME, image_data_url("WEBP"))

	def test_a_save_over_a_page_changed_elsewhere_is_refused(self):
		stale = get_editor(SUMMER_THEME)["revision"]
		save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Saved Elsewhere"))

		for endpoint in (theme_layout_api.save_draft, theme_layout_api.publish):
			with self.subTest(endpoint.__name__), self.assertRaises(frappe.TimestampMismatchError):
				endpoint(SUMMER_THEME, "index", self.edited_layout("ZZ Stale Heading"), stale)

		self.assertEqual(get_editor(SUMMER_THEME)["draft_layout"], self.edited_layout("ZZ Saved Elsewhere"))
		fresh = get_editor(SUMMER_THEME)["revision"]
		theme_layout_api.save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Fresh Heading"), fresh)


class TestThemeThumbnail(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(self.delete_thumbnail_files)
		self.addCleanup(frappe.set_user, "Administrator")
		self.delete_thumbnail_files()

	def delete_thumbnail_files(self):
		frappe.db.set_value(
			"Shop Theme", SUMMER_THEME, {"thumbnail": None, "thumbnail_dark": None}, update_modified=False
		)
		for fieldname in ("thumbnail", "thumbnail_dark"):
			for file_name in self.thumbnail_files(fieldname):
				frappe.delete_doc("File", file_name, ignore_permissions=True)

	def thumbnail_files(self, fieldname="thumbnail"):
		return frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Shop Theme",
				"attached_to_name": SUMMER_THEME,
				"attached_to_field": fieldname,
			},
			pluck="name",
		)

	def test_save_thumbnail_attaches_a_public_image_without_touching_modified(self):
		modified = frappe.db.get_value("Shop Theme", SUMMER_THEME, "modified")

		file_url = save_thumbnail(SUMMER_THEME, image_data_url("WEBP"))

		self.assertEqual(frappe.db.get_value("Shop Theme", SUMMER_THEME, "thumbnail"), file_url)
		self.assertEqual(frappe.db.get_value("Shop Theme", SUMMER_THEME, "modified"), modified)
		thumbnail = frappe.get_doc("File", {"file_url": file_url})
		self.assertFalse(thumbnail.is_private)
		self.assertTrue(file_url.endswith(".webp"))
		self.assertTrue(thumbnail.exists_on_disk())

	def test_save_thumbnail_replaces_the_previous_file(self):
		first_url = save_thumbnail(SUMMER_THEME, image_data_url("WEBP", "red"))
		first_file = frappe.get_doc("File", {"file_url": first_url})

		second_url = save_thumbnail(SUMMER_THEME, image_data_url("PNG", "blue"))

		self.assertEqual(self.thumbnail_files(), [frappe.db.get_value("File", {"file_url": second_url})])
		self.assertFalse(frappe.db.exists("File", first_file.name))
		self.assertNotEqual(second_url, first_url)
		self.assertEqual(frappe.db.get_value("Shop Theme", SUMMER_THEME, "thumbnail"), second_url)

	def test_save_thumbnail_keeps_the_light_and_the_dark_image_apart(self):
		light_url = save_thumbnail(SUMMER_THEME, image_data_url("WEBP", "white"))
		first_dark_url = save_thumbnail(SUMMER_THEME, image_data_url("WEBP", "black"), scheme="dark")
		dark_url = save_thumbnail(SUMMER_THEME, image_data_url("PNG", "black"), scheme="dark")

		thumbnails = frappe.db.get_value("Shop Theme", SUMMER_THEME, ["thumbnail", "thumbnail_dark"])
		self.assertEqual(thumbnails, (light_url, dark_url))
		self.assertEqual(self.thumbnail_files(), [frappe.db.get_value("File", {"file_url": light_url})])
		self.assertEqual(
			self.thumbnail_files("thumbnail_dark"), [frappe.db.get_value("File", {"file_url": dark_url})]
		)
		self.assertFalse(frappe.db.exists("File", {"file_url": first_dark_url}))

	def test_save_thumbnail_refuses_an_unknown_scheme(self):
		self.assertRaises(
			frappe.ValidationError, save_thumbnail, SUMMER_THEME, image_data_url("WEBP"), scheme="sepia"
		)
		self.assertEqual(frappe.db.get_value("Shop Theme", SUMMER_THEME, "thumbnail"), None)
		self.assertEqual(self.thumbnail_files(), [])

	def test_save_thumbnail_refuses_anything_but_an_image(self):
		not_an_image = f"data:image/webp;base64,{base64.b64encode(b'<svg onload=alert(1)>').decode()}"

		self.assertRaises(frappe.ValidationError, save_thumbnail, SUMMER_THEME, not_an_image)
		self.assertEqual(self.thumbnail_files(), [])

	def test_save_thumbnail_needs_an_editable_theme(self):
		image = image_data_url("WEBP")

		self.assertRaises(frappe.ValidationError, save_thumbnail, CLASSIC_THEME, image)
		self.assertRaises(frappe.DoesNotExistError, save_thumbnail, "zz-no-such-theme", image)
