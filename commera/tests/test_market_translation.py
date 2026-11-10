from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera import seo
from commera.localization import CURRENT, MISSING, OUTDATED, pin_localization, register, resolve, translate
from commera.og import generator
from commera.sdk import catalog
from commera.tests.test_content_translation import PRODUCT, use_storefront_language
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_markets import UAE, make_market, use_markets
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.www import og_image_render
from commera.www.products import details

NOTE_RESOURCE = {"type": "note", "doctype": "Note", "fields": ["title"], "label": "Notes"}


def set_up_market_translations(test):
	"""Gulf sells in Arabic to the UAE. Levant, disabled, sells in Arabic to Jordan."""
	use_storefront_languages(test, "en", published=("en", "ar"))
	use_markets(test)
	make_market("Gulf", [UAE], "ar", ["en"], handle="gulf")
	make_market("Levant", ["Jordan"], "ar", enabled=0, handle="levant")


def as_pair(value) -> tuple[str, str]:
	return (value.value, value.status)


class TestMarketTranslationLookup(IntegrationTestCase):
	def setUp(self):
		set_up_market_translations(self)
		hooks = {**frappe.get_hooks("commera_hooks", {}), "translatable_resources": [NOTE_RESOURCE]}
		self.enterContext(self.patch_hooks({"commera_hooks": hooks}))
		self.gulf = resolve("/ar-ae")[0]
		self.primary = resolve("/ar")[0]
		self.note = self.make_note("Packing note")

	def make_note(self, title):
		title = f"{title} {frappe.generate_hash(length=6)}"
		return frappe.get_doc({"doctype": "Note", "title": title}).insert()

	def title(self, note, localization):
		return as_pair(translate([note], ["title"], localization)[0]["title"])

	def add_frappe_translation(self, source, translated):
		translation = {"doctype": "Translation", "language": "ar", "source_text": source}
		translation = frappe.get_doc({**translation, "translated_text": translated}).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

	def test_the_market_translation_wins_in_its_market_only(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة")
		register("Note", self.note.name, "title", "ar", "ملاحظة الخليج", market="gulf")

		self.assertEqual(self.title(self.note, self.gulf), ("ملاحظة الخليج", CURRENT))
		self.assertEqual(self.title(self.note, self.primary), ("ملاحظة", CURRENT))

	def test_without_a_market_translation_the_lookup_falls_back_in_order(self):
		shop_wide, frappe_translated, untranslated = (self.make_note(label) for label in "ABC")
		register("Note", shop_wide.name, "title", "ar", "ملاحظة")
		self.add_frappe_translation(frappe_translated.title, "ملاحظة فرابيه")

		titles = translate([shop_wide, frappe_translated, untranslated], ["title"], self.gulf)

		self.assertEqual(
			[as_pair(fields["title"]) for fields in titles],
			[("ملاحظة", CURRENT), ("ملاحظة فرابيه", MISSING), (untranslated.title, MISSING)],
		)

	def test_an_empty_market_translation_falls_back_to_the_shop_wide_one(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة")
		register("Note", self.note.name, "title", "ar", "", market="gulf")

		self.assertEqual(self.title(self.note, self.gulf), ("ملاحظة", CURRENT))

	def test_another_markets_translation_is_never_used(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة الشام", market="levant")

		self.assertEqual(self.title(self.note, self.gulf), (self.note.title, MISSING))
		self.assertEqual(self.title(self.note, self.primary), (self.note.title, MISSING))

	def test_each_market_translation_has_its_own_status(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة الخليج", market="gulf")
		frappe.db.set_value("Note", self.note.name, "title", "Packing note v2")
		self.note.reload()
		register("Note", self.note.name, "title", "ar", "ملاحظة")

		self.assertEqual(self.title(self.note, self.gulf), ("ملاحظة الخليج", OUTDATED))
		self.assertEqual(self.title(self.note, self.primary), ("ملاحظة", CURRENT))

	def test_primary_names_the_shop_wide_translation(self):
		first = register("Note", self.note.name, "title", "ar", "أولى", market="primary")
		second = register("Note", self.note.name, "title", "ar", "ثانية", market="PRIMARY")

		self.assertEqual(first, second)
		self.assertEqual(frappe.db.get_value("Content Translation", first, "market"), "")
		self.assertEqual(self.title(self.note, self.gulf), ("ثانية", CURRENT))

	def test_a_translation_for_a_market_that_does_not_exist_is_refused(self):
		with self.assertRaisesRegex(frappe.DoesNotExistError, "Market .*nowhere.* does not exist"):
			register("Note", self.note.name, "title", "ar", "ملاحظة", market="nowhere")
		with self.assertRaises(frappe.DoesNotExistError):
			frappe.get_doc(
				{
					"doctype": "Content Translation",
					"reference_doctype": "Note",
					"reference_name": self.note.name,
					"reference_field": "title",
					"language": "ar",
					"market": "nowhere",
					"translated_value": "ملاحظة",
				}
			).insert()

	def test_market_spellings_are_one_key(self):
		first = register("Note", self.note.name, "title", "ar", "أولى", market="Gulf")
		second = register("Note", self.note.name, "title", "ar", "ثانية", market="gulf")

		self.assertEqual(first, second)
		self.assertEqual(frappe.db.get_value("Content Translation", first, "market"), "gulf")

	def test_a_disabled_market_translation_shows_in_an_admin_preview_only(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة")
		register("Note", self.note.name, "title", "ar", "ملاحظة الشام", market="levant")
		shopper = resolve("/", "ar", country="JO")[0]
		preview = resolve("/ar-jo", include_unpublished=True)[0]

		self.assertTrue(shopper.market.is_primary)
		self.assertEqual(self.title(self.note, shopper), ("ملاحظة", CURRENT))
		self.assertEqual(preview.market.handle, "levant")
		self.assertEqual(self.title(self.note, preview), ("ملاحظة الشام", CURRENT))

	def test_a_market_overrides_the_default_language(self):
		register("Note", self.note.name, "title", "en", "Gulf packing note", market="gulf")
		other = self.make_note("Other note")
		gulf_english = resolve("/en-ae")[0]

		titles = translate([self.note, other], ["title"], gulf_english)

		self.assertEqual(
			[as_pair(fields["title"]) for fields in titles],
			[("Gulf packing note", CURRENT), (other.title, CURRENT)],
		)
		self.assertEqual(self.title(self.note, resolve("/")[0]), (self.note.title, CURRENT))

	def test_the_default_language_has_no_shop_wide_translation(self):
		register("Note", self.note.name, "title", "en", "Shop-wide note")

		self.assertEqual(self.title(self.note, resolve("/en-ae")[0]), (self.note.title, CURRENT))

	def test_deleting_a_market_deletes_its_translations(self):
		register("Note", self.note.name, "title", "ar", "ملاحظة")
		register("Note", self.note.name, "title", "ar", "ملاحظة الخليج", market="gulf")

		frappe.delete_doc("Commera Market", "gulf", ignore_permissions=True)

		markets = frappe.get_all("Content Translation", {"reference_name": self.note.name}, pluck="market")
		self.assertEqual(markets, [""])


class TestMarketProductTitles(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		set_up_market_translations(self)

	def make_gulf_product(self):
		"""A product with an Arabic title, and its own title and meta description in the Gulf."""
		route = self.make_priced_variant("MARKET", default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الخليج", market="gulf")
		register(PRODUCT, product.name, "meta_description", "ar", "وصف الخليج", market="gulf")
		return product

	def serve_card(self, route, path):
		"""The cached file /<path>/og-image/<route>.png redirects to. Nothing renders or is written."""
		with (
			pin_localization(resolve(path)[0]),
			patch.object(og_image_render, "render_card_for_doc", return_value=b"png"),
			patch.object(og_image_render, "write_cache"),
			self.assertRaises(frappe.Redirect),
		):
			og_image_render.serve_og_image(route)
		return frappe.local.flags.redirect_location

	def test_a_product_card_has_the_market_title_and_its_own_url_and_cache_file(self):
		product = self.make_gulf_product()
		register(PRODUCT, product.name, "display_name", "en", "Gulf Linen Shirt", market="gulf")
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)

		with pin_localization(resolve("/en-ae")[0]):
			self.assertEqual(
				generator.build_variant_card_context(product)["display_name"], "Gulf Linen Shirt"
			)
			self.assertEqual(seo.get_product_og_image(product.route), f"/en-ae/og-image/{product.route}.png")
		with pin_localization(resolve("/ar-ae")[0]):
			self.assertEqual(seo.get_product_og_image(product.route), f"/ar-ae/og-image/{product.route}.png")
		cards = {self.serve_card(product.route, path) for path in ("/en-ae", "/")}
		self.assertEqual(len(cards), 2)

	def test_a_right_to_left_card_keeps_the_source_language_of_its_market(self):
		product = self.make_gulf_product()
		register(PRODUCT, product.name, "display_name", "en", "Gulf Linen Shirt", market="gulf")
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)

		# Satori cannot draw Arabic, so the card text stays in the store's default language.
		with pin_localization(resolve("/ar-ae")[0]):
			self.assertEqual(
				generator.build_variant_card_context(product)["display_name"], "Gulf Linen Shirt"
			)
		with pin_localization(resolve("/ar")[0]):
			self.assertEqual(
				generator.build_variant_card_context(product)["display_name"], product.display_name
			)
		self.assertEqual(self.serve_card(product.route, "/ar-ae"), self.serve_card(product.route, "/en-ae"))
		self.assertEqual(self.serve_card(product.route, "/ar"), self.serve_card(product.route, "/"))

	def test_the_legacy_product_page_seo_reads_the_market_content(self):
		product = self.make_gulf_product()
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(route=product.route, _lang="ar", _country="AE")
		frappe.local.request_cache.clear()
		context = frappe._dict()

		details.get_context(context)

		self.assertEqual(context.seo["title"], f"قميص الخليج | {seo.get_store_name()}")
		self.assertEqual(context.seo["description"], "وصف الخليج")
		self.assertIn(f"/ar-ae/og-image/{product.route}.png", context.seo["image"])
		self.assertEqual(
			(context.json_ld[0]["name"], context.json_ld[0]["description"]), ("قميص الخليج", "وصف الخليج")
		)

	def test_the_sdk_reads_the_market_title_of_a_market_request(self):
		route = self.make_priced_variant("MARKET", default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الخليج", market="gulf")
		use_storefront_language(self, "ar")

		self.assertEqual(catalog.get_product(route)["title"], "قميص الكتان")
		self.addCleanup(frappe.form_dict.pop, "_country", None)
		frappe.form_dict["_country"] = "AE"
		frappe.local.request_cache.clear()
		self.assertEqual(catalog.get_product_cards_for([product.name])[0]["title"], "قميص الخليج")
		self.assertEqual(catalog.get_product(route)["title"], "قميص الخليج")
