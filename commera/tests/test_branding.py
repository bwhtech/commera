# Copyright (c) 2026, company@bwhstudios.com and contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera import branding, seo
from commera.api.admin import settings as admin_settings
from commera.patches import sync_brand_assets_to_website_settings

WEBSITE_BRAND_FIELDS = ("banner_image", "footer_logo", "favicon")
LEGACY_BRAND_FIELDS = ("brand_logo", "footer_logo", "favicon")


def set_brand_settings(website=None, legacy=None):
	"""Write both settings singles and drop every cache the resolver reads through."""
	for fieldname in WEBSITE_BRAND_FIELDS:
		frappe.db.set_single_value(branding.WEBSITE_SETTINGS, fieldname, (website or {}).get(fieldname, ""))
	for fieldname in LEGACY_BRAND_FIELDS:
		frappe.db.set_single_value(branding.LEGACY_SETTINGS, fieldname, (legacy or {}).get(fieldname, ""))

	frappe.clear_document_cache(branding.WEBSITE_SETTINGS, branding.WEBSITE_SETTINGS)
	frappe.clear_document_cache(branding.LEGACY_SETTINGS, branding.LEGACY_SETTINGS)
	request_cache = getattr(frappe.local, "request_cache", None)
	if request_cache:
		request_cache.clear()


class TestBrandAssetResolution(IntegrationTestCase):
	def test_website_settings_wins_over_legacy(self):
		set_brand_settings(
			website={
				"banner_image": "/files/website-logo.png",
				"footer_logo": "/files/website-footer.png",
				"favicon": "/files/website-favicon.png",
			},
			legacy={
				"brand_logo": "/files/legacy-logo.png",
				"footer_logo": "/files/legacy-footer.png",
				"favicon": "/files/legacy-favicon.png",
			},
		)

		assets = branding.get_brand_assets()
		self.assertEqual(assets.logo, "/files/website-logo.png")
		self.assertEqual(assets.footer_logo, "/files/website-footer.png")
		self.assertEqual(assets.favicon, "/files/website-favicon.png")

	def test_legacy_settings_used_when_website_settings_empty(self):
		# Existing sites branded through Commera Settings must not go blank on upgrade.
		set_brand_settings(
			legacy={
				"brand_logo": "/files/legacy-logo.png",
				"footer_logo": "/files/legacy-footer.png",
				"favicon": "/files/legacy-favicon.png",
			}
		)

		assets = branding.get_brand_assets()
		self.assertEqual(assets.logo, "/files/legacy-logo.png")
		self.assertEqual(assets.footer_logo, "/files/legacy-footer.png")
		self.assertEqual(assets.favicon, "/files/legacy-favicon.png")

	def test_bundled_defaults_when_nothing_is_set(self):
		set_brand_settings()

		assets = branding.get_brand_assets()
		self.assertEqual(assets.logo, branding.BUNDLED_LOGO)
		self.assertEqual(assets.footer_logo, branding.BUNDLED_FOOTER_LOGO)
		self.assertEqual(assets.favicon, branding.BUNDLED_FAVICON)

	def test_footer_falls_back_to_the_brand_logo(self):
		set_brand_settings(website={"banner_image": "/files/website-logo.png"})

		self.assertEqual(branding.get_brand_assets().footer_logo, "/files/website-logo.png")

	def test_configured_assets_stay_empty_when_unset(self):
		# If this answered with the bundled default, the Organization JSON-LD would claim Commera's mark as its logo.
		set_brand_settings()

		self.assertEqual(branding.get_configured_brand_assets()["favicon"], "")
		self.assertIn(seo.DEFAULT_OG_IMAGE, seo.default_seo()["image"])

	def test_favicon_never_becomes_the_share_image(self):
		# A 32px favicon stretched onto a 1200x630 link preview is worse than the generated store card.
		set_brand_settings(website={"favicon": "/files/website-favicon.png"})
		frappe.db.set_single_value(branding.LEGACY_SETTINGS, "default_share_image", "")
		frappe.clear_document_cache(branding.LEGACY_SETTINGS, branding.LEGACY_SETTINGS)

		self.assertIn(seo.DEFAULT_OG_IMAGE, seo.default_seo()["image"])


class TestSyncBrandAssetsPatch(IntegrationTestCase):
	def test_copies_legacy_values_into_empty_website_settings(self):
		set_brand_settings(
			legacy={"brand_logo": "/files/legacy-logo.png", "favicon": "/files/legacy-favicon.png"}
		)

		sync_brand_assets_to_website_settings.execute()

		website_settings = frappe.get_doc(branding.WEBSITE_SETTINGS)
		self.assertEqual(website_settings.banner_image, "/files/legacy-logo.png")
		self.assertEqual(website_settings.favicon, "/files/legacy-favicon.png")
		self.assertFalse(website_settings.footer_logo)

	def test_second_run_changes_nothing(self):
		set_brand_settings(legacy={"brand_logo": "/files/legacy-logo.png"})

		sync_brand_assets_to_website_settings.execute()
		after_first_run = frappe.get_doc(branding.WEBSITE_SETTINGS).modified

		sync_brand_assets_to_website_settings.execute()
		self.assertEqual(frappe.get_doc(branding.WEBSITE_SETTINGS).modified, after_first_run)

	def test_never_overwrites_a_website_settings_value(self):
		set_brand_settings(
			website={"banner_image": "/files/website-logo.png"},
			legacy={"brand_logo": "/files/legacy-logo.png"},
		)

		sync_brand_assets_to_website_settings.execute()

		self.assertEqual(frappe.get_doc(branding.WEBSITE_SETTINGS).banner_image, "/files/website-logo.png")


class TestStoreSettingsApi(IntegrationTestCase):
	def test_reads_branding_off_website_settings_under_the_old_keys(self):
		set_brand_settings(
			website={"banner_image": "/files/website-logo.png", "favicon": "/files/website-favicon.png"},
			legacy={"brand_logo": "/files/legacy-logo.png"},
		)

		store_settings = admin_settings.get_store_settings()
		self.assertEqual(store_settings["brand_logo"], "/files/website-logo.png")
		self.assertEqual(store_settings["favicon"], "/files/website-favicon.png")
		self.assertEqual(set(admin_settings.STORE_DETAIL_FIELDS) - set(store_settings), set())

	def test_saves_branding_to_website_settings_and_leaves_legacy_alone(self):
		set_brand_settings(legacy={"brand_logo": "/files/legacy-logo.png"})

		saved = admin_settings.save_store_settings(brand_logo="/files/dashboard-logo.png")

		self.assertEqual(saved["brand_logo"], "/files/dashboard-logo.png")
		self.assertEqual(
			frappe.db.get_single_value(branding.WEBSITE_SETTINGS, "banner_image"),
			"/files/dashboard-logo.png",
		)
		self.assertEqual(
			frappe.db.get_single_value(branding.LEGACY_SETTINGS, "brand_logo"), "/files/legacy-logo.png"
		)

	def test_a_blank_store_name_is_refused(self):
		"""A blank store name silently rebrands the live site: the storefront then renders "Store"."""
		frappe.db.set_single_value(branding.LEGACY_SETTINGS, "store_name", "Summer")

		for blank in ("", "   "):
			with self.subTest(store_name=blank):
				with self.assertRaises(frappe.MandatoryError):
					admin_settings.save_store_settings(store_name=blank)

		self.assertEqual(frappe.db.get_single_value(branding.LEGACY_SETTINGS, "store_name"), "Summer")

	def test_a_real_store_name_still_saves(self):
		saved = admin_settings.save_store_settings(store_name="Summer")

		self.assertEqual(saved["store_name"], "Summer")
		self.assertEqual(frappe.db.get_single_value(branding.LEGACY_SETTINGS, "store_name"), "Summer")

	def test_a_save_that_does_not_touch_the_store_name_is_unaffected(self):
		frappe.db.set_single_value(branding.LEGACY_SETTINGS, "store_name", "Summer")

		admin_settings.save_store_settings(contact_phone="+966500000000")

		self.assertEqual(frappe.db.get_single_value(branding.LEGACY_SETTINGS, "store_name"), "Summer")

	def test_omitted_branding_keys_are_left_untouched(self):
		set_brand_settings(website={"footer_logo": "/files/website-footer.png"})

		admin_settings.save_store_settings(store_name="Kept")

		self.assertEqual(
			frappe.db.get_single_value(branding.WEBSITE_SETTINGS, "footer_logo"),
			"/files/website-footer.png",
		)
