# Copyright (c) 2026, ivend and Contributors
# Theme engine tests: name validation, path containment, inheritance, asset resolution, routing.

import json
import os
import re
import shutil
import tempfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils.jinja import get_jenv

import commera.sdk
from commera.api.admin.theme import get_theme_settings_doctype
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	build_theme_context,
	clear_theme_cache,
	get_contained_path,
	get_theme_names,
	is_within_directory,
	render_theme_context,
	validate_theme_name,
)
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import (
	build_compiled_routes,
	seed_default_routes,
)
from commera.shop_themes.jinja_helpers import (
	format_shop_theme_css,
	shop_theme_asset_url,
	shop_theme_config,
)
from commera.shop_themes.theme_resolver import (
	ThemePageRenderer,
	build_base_context,
	find_theme_file,
	get_theme_bytecode_cache,
	get_theme_environment,
	is_dynamic_page,
	match_route,
	theme_bytecode_caches,
)
from commera.utils import get_currency_symbol, get_store_currency

APP_PATH = frappe.get_app_path("commera")
STOREFRONT_CONFIG_PATTERN = re.compile(r"window\.commera_storefront_config = (.*);")


def get_storefront_config(header_content: str) -> dict:
	return json.loads(STOREFRONT_CONFIG_PATTERN.search(header_content).group(1))


THEMES_ROOT = os.path.join(APP_PATH, "themes")


class UnitTestShopTheme(UnitTestCase):
	def test_theme_name_pattern_rejects_path_separators(self):
		self.assertRaises(frappe.ValidationError, validate_theme_name, "../etc/passwd")
		self.assertRaises(frappe.ValidationError, validate_theme_name, "foo/bar")

	def test_theme_name_pattern_accepts_letters_numbers_spaces_hyphens_underscores(self):
		validate_theme_name("Shop Default Theme")
		validate_theme_name("shop-default_theme 2")

	def test_is_within_directory_rejects_sibling_prefix_directories(self):
		self.assertFalse(is_within_directory("/tmp/themes/foo", "/tmp/themes/foo_evil"))
		self.assertTrue(is_within_directory("/tmp/themes/foo", "/tmp/themes/foo/pages/x.html"))

	def test_is_within_directory_rejects_traversal(self):
		self.assertFalse(is_within_directory("/tmp/themes/foo", "/tmp/themes/foo/../foo_evil/x"))

	def test_get_contained_path_throws_on_escape(self):
		self.assertRaises(frappe.ValidationError, get_contained_path, "/tmp/themes/foo", "..", "foo_evil")

	def test_find_theme_file_containment_checks_every_candidate(self):
		self.assertIsNone(find_theme_file(["/tmp/themes/foo"], "../foo_evil/secret.py"))


class IntegrationTestShopTheme(IntegrationTestCase):
	def test_get_theme_names_walks_child_first_and_guards_cycles(self):
		names = get_theme_names("Shop Default Theme")
		self.assertEqual(names, ["Shop Default Theme", "Shop Base Theme"])

	def setUp(self):
		self.settings = frappe.get_single("Shop Theme Settings")
		self.original_active_theme = self.settings.active_theme
		self.original_dynamic_pages_enabled = self.settings.dynamic_pages_enabled

	def tearDown(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", self.original_active_theme)
		frappe.db.set_single_value(
			"Shop Theme Settings", "dynamic_pages_enabled", self.original_dynamic_pages_enabled
		)
		frappe.clear_cache()

	def activate(self, theme_name):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", theme_name)
		frappe.clear_cache()

	def test_a_theme_name_that_scrubs_onto_an_existing_theme_is_rejected(self):
		# Validated without inserting: after_insert scaffolds real directories under the app.
		collision = frappe.new_doc("Shop Theme", theme_name="Shop-Default-Theme")
		self.assertRaises(frappe.ValidationError, collision.validate)

	def test_a_theme_validates_against_its_own_slug(self):
		frappe.get_doc("Shop Theme", "Shop Default Theme").validate()

	def test_build_theme_context_resolves_the_inheritance_chain_and_dirs(self):
		context = build_theme_context("Shop Default Theme")
		self.assertEqual(context["names"], ["Shop Default Theme", "Shop Base Theme"])
		self.assertTrue(all(os.path.isdir(theme_dir) for theme_dir in context["dirs"]))

	def test_build_theme_context_is_empty_for_no_theme(self):
		context = build_theme_context(None)
		self.assertIsNone(context["theme_name"])
		self.assertEqual(context["dirs"], [])

	def test_asset_url_falls_back_to_the_active_child_theme_not_the_root_ancestor(self):
		self.activate("Shop Default Theme")
		url = shop_theme_asset_url("no/such/file.css")
		self.assertIn("/themes/shop_default_theme/", url)
		self.assertNotIn("/themes/shop_base_theme/", url)

	def test_asset_url_resolves_an_asset_owned_by_the_parent_base_theme(self):
		self.activate("Shop Default Theme")
		url = shop_theme_asset_url("images/placeholder.svg")
		self.assertIn("/themes/shop_base_theme/images/placeholder.svg", url)

	def test_asset_url_is_empty_with_no_active_theme(self):
		self.activate(None)
		self.assertEqual(shop_theme_asset_url("images/placeholder.svg"), "")

	def test_theme_config_returns_empty_dict_when_theme_has_no_settings_doctype(self):
		self.activate("Shop Base Theme")
		self.assertEqual(shop_theme_config(), frappe._dict())

	def test_theme_config_returns_the_settings_single_for_the_active_theme(self):
		self.activate("Shop Default Theme")
		config = shop_theme_config()
		self.assertEqual(config.doctype, "Shop Default Theme Settings")

	def seeded_route_patterns(self):
		return sorted(row.url_pattern for row in frappe.get_single("Shop Theme Settings").routes)

	def test_route_table_compiles_and_matches_named_groups(self):
		# after_install seeds these, but the site may have been installed before they shipped.
		seed_default_routes()
		compiled = build_compiled_routes()
		matched_route, match = match_route(compiled["routes"], "en/products/some-slug")
		self.assertIsNotNone(matched_route)
		self.assertEqual(matched_route["template_path"], "pages/products/details.html")
		self.assertEqual(match.group("route"), "some-slug")

	def test_route_table_no_match_for_unknown_path(self):
		seed_default_routes()
		compiled = build_compiled_routes()
		matched_route, _match = match_route(compiled["routes"], "en/not-a-real-route")
		self.assertIsNone(matched_route)

	def test_invalid_regex_in_a_route_throws_on_save(self):
		settings = frappe.get_single("Shop Theme Settings")
		settings.append("routes", {"url_pattern": "(unterminated", "template_path": "pages/x.html"})
		self.assertRaises(frappe.ValidationError, settings.save)

	def test_seed_default_routes_is_idempotent_on_url_pattern(self):
		# Scoped to the settings' own rows, and compared as a list so a duplicated pattern shows up.
		seed_default_routes()
		patterns_before = self.seeded_route_patterns()

		seed_default_routes()

		self.assertEqual(self.seeded_route_patterns(), patterns_before)

	def test_seed_default_routes_never_reenables_dynamic_pages(self):
		frappe.db.set_single_value("Shop Theme Settings", "dynamic_pages_enabled", 0)
		seed_default_routes()
		self.assertEqual(frappe.db.get_single_value("Shop Theme Settings", "dynamic_pages_enabled"), 0)

	def test_is_dynamic_page_rejects_reserved_first_segments(self):
		settings = {"dynamic_pages_enabled": True}
		self.assertFalse(is_dynamic_page(settings, "api/method/x"))

	def test_is_dynamic_page_requires_a_known_language_prefix(self):
		settings = {"dynamic_pages_enabled": True}
		self.assertFalse(is_dynamic_page(settings, "not-a-lang/foo"))
		self.assertTrue(is_dynamic_page(settings, "en/foo"))

	def test_is_dynamic_page_rejects_traversal_segments(self):
		# werkzeug percent-decodes before the renderer, so %2e%2e%2f arrives as ".." verbatim.
		settings = {"routes": [], "dynamic_pages_enabled": True}
		self.assertFalse(is_dynamic_page(settings, "en/../../../etc/passwd"))
		self.assertFalse(is_dynamic_page(settings, "en/.."))
		self.assertFalse(is_dynamic_page(settings, "../en/about"))
		self.assertTrue(is_dynamic_page(settings, "en/about"))

	def test_is_dynamic_page_off_when_disabled(self):
		settings = {"dynamic_pages_enabled": False}
		self.assertFalse(is_dynamic_page(settings, "en/foo"))


class IntegrationTestThemeShadowAudit(IntegrationTestCase):
	"""A theme shipping its own copy of a shared include silently disconnects the menu/footer editors."""

	def is_one_line_passthrough(self, absolute_path, app_relative_path):
		# A bare {% include "templates/<same path>" %} delegates to the real file, so it is not a shadow.
		with open(absolute_path) as theme_file:
			content = theme_file.read().strip()
		expected = '{%% include "templates/%s" %%}' % app_relative_path
		return content == expected

	def test_no_theme_shadows_an_app_template(self):
		templates_root = os.path.join(APP_PATH, "templates")
		shadowed = []

		for theme_slug in os.listdir(THEMES_ROOT):
			theme_dir = os.path.join(THEMES_ROOT, theme_slug)
			if not os.path.isdir(theme_dir):
				continue
			for root, _dirs, files in os.walk(theme_dir):
				for filename in files:
					absolute_path = os.path.join(root, filename)
					relative_path = os.path.relpath(absolute_path, theme_dir)
					candidates = {relative_path}
					if relative_path.startswith("components" + os.sep):
						candidates.add(relative_path[len("components" + os.sep) :])
					for candidate in candidates:
						if not os.path.isfile(os.path.join(templates_root, candidate)):
							continue
						if self.is_one_line_passthrough(absolute_path, candidate):
							continue
						shadowed.append((theme_slug, relative_path))

		self.assertEqual(shadowed, [], f"Theme file(s) shadow an app template: {shadowed}")


class IntegrationTestThemeBaseContract(IntegrationTestCase):
	REQUIRED_BLOCKS = ("seo", "json_ld", "analytics_head", "analytics_events", "body", "head")

	def test_every_bundled_theme_base_defines_the_required_blocks(self):
		for theme_slug in os.listdir(THEMES_ROOT):
			base_path = os.path.join(THEMES_ROOT, theme_slug, "components", "base.html")
			if not os.path.isfile(base_path):
				continue
			with open(base_path) as base_file:
				source = base_file.read()
			for block_name in self.REQUIRED_BLOCKS:
				self.assertIsNotNone(
					re.search(r"\{%-?\s*block\s+" + block_name + r"\s*-?%\}", source),
					f"{theme_slug}/components/base.html is missing the required '{block_name}' block",
				)


class IntegrationTestThemeEnvironmentIsolation(IntegrationTestCase):
	"""The theme environment must carry THIS request's identity, never the first request's.
	A jinja overlay holds its globals dict, and jinja memoises a context-less {% import %} on the Template."""

	def setUp(self):
		self.theme_dir = tempfile.mkdtemp(prefix="shop_theme_isolation_")
		self.addCleanup(self.remove_theme_dir)
		os.makedirs(os.path.join(self.theme_dir, "components"))
		os.makedirs(os.path.join(self.theme_dir, "pages"))
		self.write_theme_file(
			"components/probe_macros.html",
			"{% macro identity() %}lang={{ frappe.lang }} user={{ frappe.session.user }}{% endmacro %}",
		)
		# Imported WITHOUT context — that is the import form jinja memoises and freezes.
		self.write_theme_file(
			"pages/probe.html",
			"{% import 'components/probe_macros.html' as probe %}"
			"top lang={{ frappe.lang }} user={{ frappe.session.user }} macro {{ probe.identity() }}",
		)
		self.original_lang = frappe.local.lang
		self.addCleanup(self.restore_request)

	def remove_theme_dir(self):
		for relative_path in ("components/probe_macros.html", "pages/probe.html"):
			os.remove(os.path.join(self.theme_dir, relative_path))
		for folder in ("components", "pages"):
			os.rmdir(os.path.join(self.theme_dir, folder))
		os.rmdir(self.theme_dir)

	def restore_request(self):
		frappe.set_user("Administrator")
		frappe.local.lang = self.original_lang

	def write_theme_file(self, relative_path, source):
		with open(os.path.join(self.theme_dir, relative_path), "w") as theme_file:
			theme_file.write(source)

	def render_as(self, user, lang):
		frappe.set_user(user)
		frappe.local.lang = lang
		# get_jenv() memoises on frappe.local; dropping it makes this call equal one fresh request.
		for local_key in ("jenv_restricted", "jenv_unrestricted"):
			if hasattr(frappe.local, local_key):
				delattr(frappe.local, local_key)

		renderer = ThemePageRenderer("probe")
		renderer.theme_dirs = [self.theme_dir]
		renderer.template_path = "pages/probe.html"
		return renderer.render_with_theme_loader(frappe._dict())

	def test_a_later_request_sees_its_own_user_and_lang_inside_a_contextless_macro(self):
		self.assertEqual(
			self.render_as("Administrator", "en"),
			"top lang=en user=Administrator macro lang=en user=Administrator",
		)
		self.assertEqual(
			self.render_as("Guest", "ar"),
			"top lang=ar user=Guest macro lang=ar user=Guest",
		)
		self.assertEqual(
			self.render_as("Administrator", "en"),
			"top lang=en user=Administrator macro lang=en user=Administrator",
		)

	def test_theme_environment_is_never_reused_across_requests(self):
		first_env = get_theme_environment(get_jenv(), [self.theme_dir])
		second_env = get_theme_environment(get_jenv(), [self.theme_dir])
		self.assertIsNot(first_env, second_env)
		self.assertIsNot(first_env.loader, second_env.loader)

	def test_theme_environment_globals_are_the_current_requests_globals(self):
		jenv = get_jenv()
		self.assertIs(get_theme_environment(jenv, [self.theme_dir]).globals, jenv.globals)

	def test_bytecode_cache_is_scoped_to_the_site(self):
		# Theme dirs resolve identically on every site, so an unkeyed cache would be bench-wide.
		original_site = frappe.local.site
		self.addCleanup(setattr, frappe.local, "site", original_site)

		own_cache = get_theme_bytecode_cache()
		frappe.local.site = "another-tenant.localhost"
		self.addCleanup(theme_bytecode_caches.pop, "another-tenant.localhost", None)
		self.assertIsNot(own_cache, get_theme_bytecode_cache())


class IntegrationTestThemeBaseContext(IntegrationTestCase):
	def test_base_context_does_not_mint_a_csrf_token(self):
		# get_csrf_token() here minted a throwaway token and made a themed page differ from an unthemed one.
		self.assertNotIn("csrf_token", build_base_context(None))

	def test_base_context_loads_the_storefront_sdk(self):
		header_content = build_base_context(None).commera_header_content
		self.assertIn("window.commera_storefront_config", header_content)
		self.assertIn("commera-storefront.bundle", header_content)

	def test_header_content_carries_each_session_its_own_csrf_token(self):
		session_data = frappe.local.session.data
		self.addCleanup(setattr, session_data, "csrf_token", session_data.get("csrf_token"))

		session_data.csrf_token = "shopper-one-token"
		self.assertIn('"csrf_token": "shopper-one-token"', build_base_context(None).commera_header_content)
		session_data.csrf_token = "shopper-two-token"
		self.assertIn('"csrf_token": "shopper-two-token"', build_base_context(None).commera_header_content)

	def test_header_content_knows_the_currency_of_every_enabled_selling_price_list(self):
		for currency, selling, enabled in (("SAR", 1, 1), ("AED", 0, 1), ("EUR", 1, 0)):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": f"Header Currency {currency} {frappe.generate_hash(length=6)}",
					"currency": currency,
					"selling": selling,
					"buying": int(not selling),
					"enabled": enabled,
				}
			).insert(ignore_permissions=True)
		frappe.local.request_cache.clear()

		config = get_storefront_config(build_base_context(None).commera_header_content)

		selling_currencies = frappe.get_all(
			"Price List", filters={"enabled": 1, "selling": 1}, pluck="currency", distinct=True
		)
		self.assertEqual(set(config["currency_symbols"]), {*selling_currencies, get_store_currency()})
		self.assertEqual(
			config["currency_symbols"]["SAR"], '<span class="saudi-currency-symbol pe-0.5"></span>'
		)
		self.assertNotIn("AED", config["currency_symbols"])
		self.assertNotIn("EUR", config["currency_symbols"])
		self.assertEqual(config["store_currency"], get_store_currency())
		self.assertEqual(
			config["currency_symbols"][get_store_currency()], get_currency_symbol(get_store_currency())
		)

	def test_header_content_does_not_mint_a_csrf_token_for_a_guest(self):
		session_data = frappe.local.session.data
		self.addCleanup(setattr, session_data, "csrf_token", session_data.get("csrf_token"))

		session_data.csrf_token = None
		self.assertIn('"csrf_token": null', build_base_context(None).commera_header_content)
		self.assertIsNone(session_data.csrf_token)

	def test_base_context_gives_the_frame_the_sdk_as_commera(self):
		self.assertIs(build_base_context(None).commera, commera.sdk)


class IntegrationTestThemedRendering(IntegrationTestCase):
	def setUp(self):
		self.settings = frappe.get_single("Shop Theme Settings")
		self.original_active_theme = self.settings.active_theme

	def tearDown(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", self.original_active_theme)
		frappe.clear_cache()

	def activate(self, theme_name):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", theme_name)
		frappe.clear_cache()

	def test_themed_and_unthemed_product_card_render_the_same_fields(self):
		from commera.shop_themes.render import render_themed_template

		card_context = {
			"image": "/files/sample.jpg",
			"brand": "Sample",
			"product_name": "Sample Product",
			"formatted_price": 100.0,
			"original_price": 0,
			"discount": 0,
		}

		self.activate(None)
		unthemed_html = render_themed_template(
			'{% from "templates/macros/item_card.html" import item_card %}'
			"{{ item_card(image, brand, product_name, formatted_price, original_price, discount) }}",
			card_context,
		)

		self.activate("Shop Default Theme")
		themed_html = render_themed_template(
			'{% from "components/macros/product_card.html" import product_card %}'
			"{{ product_card(image, brand, product_name, formatted_price, original_price, discount) }}",
			card_context,
		)

		for expected in ("Sample Product", "sample.jpg"):
			self.assertIn(expected, unthemed_html)
			self.assertIn(expected, themed_html)

	def test_og_card_still_renders_with_no_active_theme(self):
		from commera.shop_themes.render import render_themed_template

		self.activate(None)
		html = render_themed_template("<html><body>{{ label }}</body></html>", {"label": "card"})
		self.assertIn("card", html)

	def test_render_themed_template_falls_back_when_theme_has_no_dirs(self):
		from commera.shop_themes.render import render_themed_template

		self.activate("Shop Default Theme")
		html = render_themed_template("<html><body>{{ label }}</body></html>", {"label": "card"})
		self.assertIn("card", html)


class IntegrationTestThemedNotFound(IntegrationTestCase):
	def setUp(self):
		self.theme_dir = tempfile.mkdtemp(prefix="shop_theme_not_found_")
		self.addCleanup(shutil.rmtree, self.theme_dir)
		os.makedirs(os.path.join(self.theme_dir, "pages"))
		self.write_theme_file("pages/probe.html", "found")
		self.write_theme_file(
			"pages/probe.py",
			"import frappe\n\n\ndef get_context(context):\n\traise frappe.DoesNotExistError\n",
		)

	def write_theme_file(self, relative_path, source):
		with open(os.path.join(self.theme_dir, relative_path), "w") as theme_file:
			theme_file.write(source)

	def render_probe(self):
		renderer = ThemePageRenderer("en/probe")
		renderer.theme_dirs = [self.theme_dir]
		renderer.template_path = "pages/probe.html"
		return renderer.render()

	def test_a_missing_record_renders_the_theme_404_uncached(self):
		self.write_theme_file("pages/404.html", "theme not found")

		response = self.render_probe()

		self.assertEqual(response.status_code, 404)
		self.assertEqual(response.headers["Cache-Control"], "no-store")
		self.assertEqual(response.get_data(as_text=True), "theme not found")

	def test_a_theme_without_404_html_leaves_the_miss_to_frappe(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self.render_probe()


class IntegrationTestThemeSettingsContext(IntegrationTestCase):
	settings_doctype = "Test Theme Settings Context"

	def setUp(self):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": self.settings_doctype,
				"module": "Shop Themes",
				"custom": 1,
				"issingle": 1,
				"fields": [
					{"fieldname": "tagline", "fieldtype": "Data", "label": "Tagline"},
					{"fieldname": "style_tab", "fieldtype": "Tab Break", "label": "Style"},
					{"fieldname": "accent_color", "fieldtype": "Color", "label": "Accent"},
					{"fieldname": "body_font", "fieldtype": "Data", "label": "Body Font"},
					{"fieldname": "font_weight", "fieldtype": "Int", "label": "Font Weight"},
					{"fieldname": "card_radius", "fieldtype": "Data", "label": "Card Radius"},
					{
						"fieldname": "card_shadows",
						"fieldtype": "Table",
						"label": "Card Shadows",
						"options": "Has Role",
					},
					{"fieldname": "other_tab", "fieldtype": "Tab Break", "label": "Other"},
					{"fieldname": "footer_note", "fieldtype": "Data", "label": "Footer Note"},
				],
				"permissions": [{"role": "System Manager", "read": 1, "write": 1}],
			}
		).insert()
		self.save_settings(
			accent_color="#0f766e",
			body_font='"Inter Tight", sans-serif',
			font_weight=600,
			card_radius="1.5rem",
			tagline="Hi",
			footer_note="Bye",
		)
		self.original_active_theme = frappe.db.get_single_value("Shop Theme Settings", "active_theme")
		frappe.db.set_value("Shop Theme", "Shop Base Theme", "theme_settings", self.settings_doctype)
		frappe.db.set_value("Shop Theme", "Shop Default Theme", "theme_settings", None)
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", "Shop Default Theme")
		frappe.clear_cache()
		self.addCleanup(self.restore)

	def restore(self):
		frappe.db.rollback()
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", self.original_active_theme)
		frappe.clear_cache()

	def save_settings(self, **values):
		settings = frappe.get_doc(self.settings_doctype)
		settings.update(values)
		settings.save()

	def test_a_child_without_settings_falls_back_to_its_parents(self):
		self.assertEqual(build_theme_context("Shop Default Theme")["settings_doctype"], self.settings_doctype)
		self.assertEqual(get_theme_settings_doctype("Shop Default Theme"), self.settings_doctype)

	def test_a_child_with_settings_uses_its_own(self):
		frappe.db.set_value(
			"Shop Theme", "Shop Default Theme", "theme_settings", "Shop Default Theme Settings"
		)
		clear_theme_cache()
		self.assertEqual(
			build_theme_context("Shop Default Theme")["settings_doctype"], "Shop Default Theme Settings"
		)

	def test_a_settings_doctype_that_is_not_installed_falls_through_to_the_parent(self):
		frappe.db.set_value("Shop Theme", "Shop Default Theme", "theme_settings", "No Such Theme Settings")
		self.assertEqual(build_theme_context("Shop Default Theme")["settings_doctype"], self.settings_doctype)

	def test_a_classic_page_gets_the_settings_as_theme(self):
		context = build_base_context(None)
		self.assertEqual(context.theme.tagline, "Hi")
		self.assertEqual(context.theme.font_weight, 600)

	def test_every_style_tab_field_becomes_a_css_variable_as_typed(self):
		self.assertEqual(
			format_shop_theme_css(),
			'<style id="shop-theme-settings">:root{--theme-accent-color: #0f766e; '
			'--theme-body-font: "Inter Tight", sans-serif; --theme-font-weight: 600; '
			"--theme-card-radius: 1.5rem;}</style>",
		)

	def test_values_that_could_break_out_of_the_style_tag_are_dropped(self):
		self.save_settings(
			accent_color="</style><script>alert(1)</script>",
			body_font="Inter; } body { display: none",
			card_radius="1rem /* x",
		)
		self.assertEqual(
			format_shop_theme_css(),
			'<style id="shop-theme-settings">:root{--theme-font-weight: 600;}</style>',
		)

	def test_a_theme_without_settings_emits_no_style(self):
		frappe.db.set_value("Shop Theme", "Shop Base Theme", "theme_settings", None)
		clear_theme_cache()
		self.assertEqual(format_shop_theme_css(), "")
		self.assertEqual(build_base_context(None).theme, frappe._dict())

	def test_pages_sections_and_blocks_of_a_previewed_sections_theme_see_theme(self):
		theme_dir = tempfile.mkdtemp(prefix="shop_theme_settings_")
		self.addCleanup(shutil.rmtree, theme_dir)
		theme_files = {
			"pages/probe.html": "page={{ theme.tagline }} {{ render_layout('probe') }}",
			"sections/probe.html": (
				"section={{ theme.tagline }}{% for block in section.blocks %} block={{ theme.tagline }}{% endfor %}"
			),
			"sections/probe.json": json.dumps({"blocks": {"item": {}}}),
			"layouts/probe.json": json.dumps(
				{"sections": [{"id": "one", "type": "probe", "blocks": [{"id": "two", "type": "item"}]}]}
			),
		}
		for relative_path, source in theme_files.items():
			os.makedirs(os.path.join(theme_dir, os.path.dirname(relative_path)), exist_ok=True)
			with open(os.path.join(theme_dir, relative_path), "w") as theme_file:
				theme_file.write(source)

		previewed_theme = {
			"theme_name": "Test Theme Settings Probe",
			"theme_type": "Sections",
			"names": ["Test Theme Settings Probe"],
			"dirs": [theme_dir],
			"apps": {"Test Theme Settings Probe": "commera"},
			"settings_doctype": self.settings_doctype,
		}
		frappe.db.set_value("Shop Theme", "Shop Base Theme", "theme_settings", None)
		clear_theme_cache()
		with render_theme_context(previewed_theme):
			renderer = ThemePageRenderer("probe")
			renderer.theme_dirs = [theme_dir]
			renderer.template_path = "pages/probe.html"
			html = renderer.render_with_theme_loader(build_base_context(None))

		self.assertEqual(html, "page=Hi section=Hi block=Hi")


class IntegrationTestCreateThemeSettings(IntegrationTestCase):
	def test_the_settings_single_is_created_linked_and_raises_no_messages(self):
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		frappe.local.message_log = []
		with patch.dict(frappe.conf, {"developer_mode": 0}):
			frappe.get_doc("Shop Theme", "Shop Base Theme").create_theme_settings()

		self.assertEqual(
			frappe.db.get_value("Shop Theme", "Shop Base Theme", "theme_settings"), "Shop Base Theme Settings"
		)
		self.assertTrue(frappe.db.get_value("DocType", "Shop Base Theme Settings", "issingle"))
		self.assertTrue(frappe.get_meta("Shop Base Theme Settings").get_field("style_tab"))
		self.assertEqual(frappe.local.message_log, [])
