import frappe
from frappe.tests import IntegrationTestCase

from commera.commera_ecommerce.doctype.commera_settings.footer import footer_preview
from commera.localization import get_translatable_fields, register, resolve
from commera.localization.content import CURRENT, translate
from commera.sdk import shop
from commera.shop_data import get_header_data
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages

SETTINGS = "Commera Settings"
SECTION = "Footer Section Config"
LINK = "Footer Link"
FOOTER_TEMPLATE = "templates/includes/footer.html"


class TestStoreFrameTranslation(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		frappe.db.set_single_value(
			SETTINGS, {"store_name": "Linen House", "default_meta_description": "Shirts for summer"}
		)
		self.section = self.make_section(
			"Help", [("Shipping", "/pages/shipping"), ("Linen care", "/returns")]
		)
		self.other = self.make_section("About", [("Story", "/pages/story")])
		self.set_footer(self.section, self.other)
		self.shipping, self.returns = self.section.footer_links

		register(SETTINGS, SETTINGS, "store_name", "ar", "بيت الكتان")
		register(SETTINGS, SETTINGS, "default_meta_description", "ar", "قمصان للصيف")
		register(SECTION, self.section.name, "section_title", "ar", "مساعدة")
		register(LINK, self.shipping.name, "link_label", "ar", "الشحن")

	def make_section(self, title, links):
		section = frappe.get_doc(
			{
				"doctype": SECTION,
				"section_title": f"{title} {frappe.generate_hash(length=8)}",
				"enabled": 1,
				"footer_links": [
					{"link_label": label, "link_url": url, "link_order": order, "enabled": 1}
					for order, (label, url) in enumerate(links, start=1)
				],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.clear_document_cache, SECTION, section.name)
		return section

	def set_footer(self, *sections):
		"""Write the footer mapping straight to the database: saving Commera Settings runs unrelated checks."""
		frappe.db.delete("Footer Section Mapping", {"parent": SETTINGS, "parentfield": "footer_sections"})
		for order, section in enumerate(sections, start=1):
			frappe.get_doc(
				{
					"doctype": "Footer Section Mapping",
					"parent": SETTINGS,
					"parenttype": SETTINGS,
					"parentfield": "footer_sections",
					"idx": order,
					"footer_section": section.name,
					"section_order": order,
					"enabled": 1,
				}
			).db_insert()
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def serve(self, language):
		use_storefront_language(self, language)

	def test_the_registry_declares_the_footer_and_the_shop_details(self):
		self.assertEqual(get_translatable_fields(SECTION), {"section_title"})
		self.assertEqual(get_translatable_fields(LINK), {"link_label"})
		self.assertEqual(get_translatable_fields(SETTINGS), {"store_name", "default_meta_description"})

	def test_a_single_and_a_child_row_are_keyed_by_their_own_names(self):
		arabic = resolve("/ar")[0]
		settings = translate(
			[{"name": SETTINGS, "store_name": "Linen House"}], ["store_name"], arabic, SETTINGS
		)
		link = translate(
			[{"name": self.shipping.name, "link_label": "Shipping"}], ["link_label"], arabic, LINK
		)

		self.assertEqual(
			(settings[0]["store_name"].value, settings[0]["store_name"].status), ("بيت الكتان", CURRENT)
		)
		self.assertEqual((link[0]["link_label"].value, link[0]["link_label"].status), ("الشحن", CURRENT))

	def test_the_shop_returns_its_translated_name_description_and_footer(self):
		self.serve("ar")
		result = shop.get_shop()

		self.assertEqual((result["name"], result["description"]), ("بيت الكتان", "قمصان للصيف"))
		self.assertEqual(
			result["footer"][0],
			{
				"title": "مساعدة",
				"links": [
					{"title": "الشحن", "url": "/pages/shipping"},
					{"title": "Linen care", "url": "/returns"},
				],
			},
		)
		self.assertEqual(result["footer"][1]["title"], self.other.section_title)

	def test_the_footer_menu_returns_translated_titles_and_source_links(self):
		self.serve("ar")
		section = shop.get_menu("footer")["items"][0]

		self.assertEqual(section["title"], "مساعدة")
		self.assertEqual(
			[(link["title"], link["target"]) for link in section["items"]],
			[("الشحن", "/pages/shipping"), ("Linen care", "/returns")],
		)

	def test_the_default_language_returns_the_source(self):
		self.serve("en")
		result = shop.get_shop()

		self.assertEqual((result["name"], result["description"]), ("Linen House", "Shirts for summer"))
		self.assertEqual(result["footer"][0]["title"], self.section.section_title)
		self.assertEqual(result["footer"][0]["links"][0]["title"], "Shipping")

	def test_the_header_shows_the_translated_store_name(self):
		self.serve("ar")
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)

		self.assertEqual(get_header_data().store_name, "بيت الكتان")

	def test_the_footer_template_renders_translations_escaped(self):
		register(LINK, self.returns.name, "link_label", "ar", "<b>الإرجاع</b>")
		html = frappe.render_template(FOOTER_TEMPLATE, {"localization": resolve("/ar")[0]})

		self.assertIn("مساعدة", html)
		self.assertIn(">الشحن</a>", html)
		self.assertIn("&lt;b&gt;الإرجاع&lt;/b&gt;", html)
		self.assertIn('href="/pages/shipping"', html)
		self.assertIn("بيت الكتان", html)

	def test_a_moved_link_keeps_its_translation(self):
		footer_preview.move_footer_link(self.section.name, self.other.name, self.shipping.name, 0)
		moved = frappe.get_doc(SECTION, self.other.name).footer_links[0]

		self.assertEqual(moved.link_label, "Shipping")
		self.assertEqual(
			frappe.db.get_value(
				"Content Translation",
				{"reference_doctype": LINK, "reference_name": moved.name},
				"translated_value",
			),
			"الشحن",
		)

	def test_deleting_a_section_deletes_its_and_its_links_translations(self):
		self.set_footer(self.other)
		frappe.delete_doc(SECTION, self.section.name, ignore_permissions=True)

		for doctype, name in ((SECTION, self.section.name), (LINK, self.shipping.name)):
			self.assertFalse(
				frappe.db.exists(
					"Content Translation", {"reference_doctype": doctype, "reference_name": name}
				)
			)
