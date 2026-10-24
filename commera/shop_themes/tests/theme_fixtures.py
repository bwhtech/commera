import json
import os
import shutil
import tempfile

import frappe

from commera.shop_themes.doctype.shop_theme.shop_theme import (
	THEME_CONTEXT_CACHE_KEY,
	render_theme_context,
)
from commera.shop_themes.layouts import LAYOUT_CACHE_KEY, LAYOUT_OVERRIDES_LOCAL_KEY
from commera.shop_themes.section_render import EDITOR_LOCAL_KEY, ERROR_THROTTLE_CACHE_PREFIX
from commera.shop_themes.theme_files import theme_file_cache

FIXTURE_THEME_NAME = "Sections Fixture Theme"


def text_setting(setting_id, default=None, **extra):
	setting = {"id": setting_id, "type": "text", "label": setting_id.title(), **extra}
	if default is not None:
		setting["default"] = default
	return setting


PARENT_FILES = {
	"settings.json": {
		"name": "Theme settings",
		"settings": [
			{"id": "accent", "type": "color", "label": "Accent", "default": "#ff0000"},
			{
				"id": "radius",
				"type": "range",
				"label": "Radius",
				"min": 0,
				"max": 24,
				"unit": "px",
				"default": 8,
			},
			text_setting("tagline", "Hello"),
		],
	},
	"sections/hero.json": {
		"name": "Hero",
		"settings": [
			text_setting("heading", {"en": "Welcome", "ar": "أهلا"}, translatable=True),
			{
				"id": "height",
				"type": "select",
				"label": "Height",
				"default": "large",
				"options": [{"value": "small", "label": "Small"}, {"value": "large", "label": "Large"}],
			},
			{"id": "count", "type": "range", "label": "Count", "min": 1, "max": 10, "default": 4},
			{"id": "autoplay", "type": "check", "label": "Autoplay", "default": True},
			{"id": "link", "type": "url", "label": "Link"},
			{"id": "accent", "type": "color", "label": "Accent"},
			{"id": "collection", "type": "collection", "label": "Collection"},
		],
		"blocks": {
			"slide": {"name": "Slide", "settings": [text_setting("title", translatable=True)]},
			"badge": {"name": "Badge", "static": True, "settings": [text_setting("label", "New")]},
		},
		"max_blocks": 4,
	},
	"sections/hero.html": (
		'{% macro slide(block) %}<p class="slide"{{ block.editor_attributes }}>{{ block.index }}:{{ block.settings.title }}</p>{% endmacro %}'
		'{% macro badge(block) %}<span class="badge"{{ block.editor_attributes }}>{{ block.settings.label }}</span>{% endmacro %}'
		'<div class="hero-{{ section.settings.height }}">{{ section.settings.heading }}'
		"{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}"
		'{{ render_static_block("badge") }}</div>'
	),
	"sections/banner.json": {"name": "Banner", "settings": [text_setting("heading", "Parent banner")]},
	"sections/banner.html": '<div class="banner-parent">{{ section.settings.heading }}</div>',
	"sections/gated.json": {
		"name": "Gated",
		"settings": [{"id": "show", "type": "check", "label": "Show", "default": False}],
	},
	"sections/gated.html": "{% if section.settings.show %}<p>shown</p>{% endif %}\n  \n",
	"sections/with_data.json": {"name": "With data", "settings": [text_setting("heading", "Data")]},
	"sections/with_data.py": (
		"def get_context(section, page):\n"
		'\treturn {"controller_heading": f"{section.settings.heading}!", '
		'"section_types": ",".join(placed.type for placed in page.layout_sections)}\n'
	),
	"sections/with_data.html": "<p>{{ controller_heading }}|{{ section_types }}|{{ page_marker }}</p>",
	"sections/broken_controller.json": {"name": "Broken controller"},
	"sections/broken_controller.py": 'def get_context(section, page):\n\traise RuntimeError("controller boom")\n',
	"sections/broken_controller.html": "<p>never</p>",
	"sections/broken_template.json": {"name": "Broken template"},
	"sections/broken_template.html": "{% set zero = 0 %}<p>{{ 1 / zero }}</p>",
	"sections/missing_macro.json": {"name": "Missing macro", "blocks": {"quote": {"name": "Quote"}}},
	"sections/missing_macro.html": "<div>{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}</div>",
	"sections/header_bar.json": {"name": "Header bar", "groups": ["header"]},
	"sections/header_bar.html": "<p>header bar</p>",
	"sections/product_only.json": {"name": "Product only", "templates": ["product"]},
	"sections/product_only.html": "<p>product only</p>",
	"sections/main.json": {"name": "Main", "static": True, "templates": ["page"]},
	"sections/main.html": "<main>main</main>",
	"sections/app_ready.json": {
		"name": "App ready",
		"accepts_apps": True,
		"blocks": {"note": {"name": "Note", "settings": [text_setting("text")]}},
	},
	"sections/app_ready.html": (
		"{% macro note(block) %}<i{{ block.editor_attributes }}>{{ block.settings.text }}</i>{% endmacro %}"
		"<div>{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}</div>"
	),
	"layouts/index.json": {
		"sections": [
			{
				"id": "hero",
				"type": "hero",
				"settings": {"height": "small"},
				"blocks": [
					{"id": "slide-1", "type": "slide", "settings": {"title": "One"}},
					{"id": "slide-2", "type": "slide", "disabled": True, "settings": {"title": "Two"}},
					{"id": "slide-3", "type": "slide", "settings": {"title": "Three"}},
					{"id": "app-1", "type": "app:some_app/size_chart", "settings": {}},
				],
			},
			{"id": "banner", "type": "banner", "settings": {}},
			{"id": "hidden", "type": "banner", "disabled": True, "settings": {"heading": "Hidden"}},
			{"id": "gone", "type": "no_longer_shipped", "settings": {}},
			{"id": "gated", "type": "gated", "settings": {}},
			{"id": "with_data", "type": "with_data", "settings": {}},
		]
	},
	"layouts/page.json": {"sections": [{"id": "main", "type": "main", "settings": {}, "blocks": []}]},
	"layouts/collection.json": {"sections": [{"id": "parent_banner", "type": "banner"}]},
}

CHILD_FILES = {
	"settings.json": {
		"name": "Theme settings",
		"settings": [
			{
				"id": "radius",
				"type": "range",
				"label": "Radius",
				"min": 0,
				"max": 40,
				"unit": "px",
				"default": 12,
			},
			{
				"id": "page_width",
				"type": "range",
				"label": "Width",
				"min": 960,
				"max": 1600,
				"unit": "px",
				"default": 1280,
			},
		],
	},
	"sections/banner.html": '<div class="banner-child">{{ section.settings.heading }}</div>',
	"sections/child_only.json": {"name": "Child only"},
	"sections/child_only.html": "<p>child only</p>",
	"layouts/collection.json": {"sections": [{"id": "child_banner", "type": "child_only"}]},
	"layouts/groups/header.json": {"sections": []},
}


def write_theme_files(theme_dir, files):
	for relative_path, content in files.items():
		path = os.path.join(theme_dir, relative_path)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w") as theme_file:
			theme_file.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))


def insert_fixture_shop_theme():
	developer_mode = frappe.conf.developer_mode
	frappe.conf.developer_mode = 0
	try:
		frappe.new_doc("Shop Theme", theme_name=FIXTURE_THEME_NAME, module="Shop Themes").insert()
	finally:
		frappe.conf.developer_mode = developer_mode


class ThemeFixtureMixin:
	def add_fixture_theme(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(theme_file_cache.clear)
		self.addCleanup(self.clear_fixture_caches)
		self.clear_fixture_caches()

		self.fixture_root = tempfile.mkdtemp(prefix="commera_theme_sections_")
		self.addCleanup(shutil.rmtree, self.fixture_root)
		self.parent_dir = os.path.join(self.fixture_root, "fixture_parent")
		self.child_dir = os.path.join(self.fixture_root, "fixture_child")
		write_theme_files(self.parent_dir, PARENT_FILES)
		write_theme_files(self.child_dir, CHILD_FILES)
		self.theme_dirs = [self.child_dir, self.parent_dir]

		insert_fixture_shop_theme()
		self.theme_name = FIXTURE_THEME_NAME
		self.theme_context = {
			"theme_name": FIXTURE_THEME_NAME,
			"names": [FIXTURE_THEME_NAME],
			"dirs": self.theme_dirs,
			"apps": {FIXTURE_THEME_NAME: "commera"},
			"settings_doctype": None,
		}
		frappe.cache.hset(THEME_CONTEXT_CACHE_KEY, FIXTURE_THEME_NAME, self.theme_context)
		self.enterContext(render_theme_context(self.theme_context))

	def clear_fixture_caches(self):
		frappe.cache.hdel(THEME_CONTEXT_CACHE_KEY, FIXTURE_THEME_NAME)
		frappe.cache.delete_value(LAYOUT_CACHE_KEY)
		frappe.cache.delete_keys(f"{ERROR_THROTTLE_CACHE_PREFIX}|{FIXTURE_THEME_NAME}")
		setattr(frappe.local, LAYOUT_OVERRIDES_LOCAL_KEY, None)
		setattr(frappe.local, EDITOR_LOCAL_KEY, None)

	def write_fixture_file(self, theme_dir, relative_path, content):
		write_theme_files(theme_dir, {relative_path: content})
