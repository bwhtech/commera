import unittest
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.website.path_resolver import resolve_redirect
from PIL import Image

from commera.api.admin.catalog import DEFAULT_OPTION_ATTRIBUTE, DEFAULT_OPTION_VALUE, ensure_attribute_exists
from commera.api.admin.onboarding import get_existing_store
from commera.commera_ecommerce.doctype.commera_settings.commera_settings import create_configurator_log
from commera.erpnext_import import get_preview, import_batch, plan_products
from commera.tests.test_product_onboarding import ProductOnboardingTestCase
from commera.webshop_migration import (
	apply_webshop_extras,
	get_webshop_published_items,
	get_webshop_store_defaults,
	has_webshop_data,
)

SHOPPER = "webshop-migration-shopper@example.com"
LONG_DESCRIPTION = "<p>Hand-stitched from organic cotton.</p>"


def get_preselected(item_code):
	(item,) = [row for row in get_preview(item_code, 0, 50)["items"] if row["item_code"] == item_code]
	return item["preselected"]


class WebshopImportTestCase(ProductOnboardingTestCase):
	def setUp(self):
		super().setUp()
		ensure_attribute_exists(DEFAULT_OPTION_ATTRIBUTE, DEFAULT_OPTION_VALUE, "STD")

	def import_items(self, item_codes):
		created = import_batch(plan_products(item_codes), create_configurator_log(), [])
		return [plan["item_code"] for plan, _configurator in created]

	def get_product(self, item_code):
		return frappe.get_doc("Style Attribute Variant", {"item_style": item_code})


class TestImportWithoutWebshop(WebshopImportTestCase):
	def setUp(self):
		super().setUp()
		patcher = patch("commera.webshop_migration.has_webshop_data", return_value=False)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_import_works_and_the_webshop_hook_does_nothing(self):
		item_code = self.make_plain_item()
		self.assertEqual(self.import_items([item_code]), [item_code])

		self.assertEqual(apply_webshop_extras([item_code]), {})
		self.assertTrue(self.get_product(item_code).route)
		self.assertIsNone(get_webshop_published_items())
		self.assertEqual(get_webshop_store_defaults(), {})

	def test_every_item_is_preselected(self):
		item_code = self.make_plain_item()
		self.assertTrue(get_preselected(item_code))


class TestWebshopMigration(WebshopImportTestCase):
	@classmethod
	def setUpClass(cls):
		if not has_webshop_data() or not frappe.db.exists("DocType", "Website Item"):
			raise unittest.SkipTest("webshop doctypes are not on this site")
		super().setUpClass()

	def setUp(self):
		super().setUp()
		self.shopper = self.make_shopper()
		self.website_image = self.make_image_file()
		self.item_code = self.make_plain_item()
		self.website_item = self.make_website_item(
			self.item_code, f"products/plain-{self.suffix.lower()}", self.make_slideshow()
		)
		self.make_item_review(self.website_item, rating=0.8)
		self.make_wishlist(self.website_item)

	def make_shopper(self):
		if not frappe.db.exists("User", SHOPPER):
			user = frappe.new_doc("User")
			user.email = SHOPPER
			user.first_name = "Webshop Shopper"
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)
		return SHOPPER

	def make_image_file(self):
		image = BytesIO()
		Image.new("RGB", (2, 2), tuple(frappe.generate_hash(length=6).encode()[:3])).save(image, "PNG")
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"{frappe.generate_hash(length=8)}.png"
		file_doc.content = image.getvalue()
		file_doc.is_private = 0
		file_doc.insert()
		return file_doc.file_url

	def make_slideshow(self):
		slideshow = frappe.new_doc("Website Slideshow")
		slideshow.slideshow_name = f"Webshop Slideshow {self.suffix}"
		for image in ("/files/front.jpg", "/files/back.jpg"):
			slideshow.append("slideshow_items", {"image": image})
		slideshow.insert(ignore_permissions=True)
		return slideshow.name

	def make_website_item(self, item_code, route, slideshow=None, published=1):
		website_item = frappe.new_doc("Website Item")
		website_item.item_code = item_code
		website_item.web_item_name = item_code
		website_item.route = route
		website_item.slideshow = slideshow
		website_item.website_image = self.website_image
		website_item.web_long_description = LONG_DESCRIPTION
		website_item.published = published
		website_item.insert(ignore_permissions=True)
		return website_item

	def make_item_review(self, website_item, rating):
		review = frappe.new_doc("Item Review")
		review.website_item = website_item.name
		review.item = website_item.item_code
		review.user = self.shopper
		review.rating = rating
		review.review_title = "Lovely"
		review.comment = "Fits well."
		review.insert(ignore_permissions=True)

	def make_wishlist(self, website_item):
		wishlist = (
			frappe.get_doc("Wishlist", self.shopper) if frappe.db.exists("Wishlist", self.shopper) else None
		)
		if not wishlist:
			wishlist = frappe.new_doc("Wishlist")
			wishlist.user = self.shopper
		wishlist.append("items", {"item_code": website_item.item_code, "website_item": website_item.name})
		wishlist.save(ignore_permissions=True)

	def migrate(self, item_codes):
		self.import_items(item_codes)
		return apply_webshop_extras(item_codes)

	def test_only_published_website_items_are_preselected(self):
		hidden_item = self.make_plain_item()
		self.make_website_item(hidden_item, f"products/hidden-{self.suffix.lower()}", published=0)

		self.assertTrue(get_preselected(self.item_code))
		self.assertFalse(get_preselected(hidden_item))

	def test_images_route_and_description_come_from_the_website_item(self):
		self.migrate([self.item_code])
		product = self.get_product(self.item_code)

		self.assertEqual([row.image for row in product.images], ["/files/front.jpg", "/files/back.jpg"])
		self.assertEqual(product.route, f"plain-{self.suffix.lower()}")
		self.assertEqual(frappe.db.get_value("Item", self.item_code, "description"), LONG_DESCRIPTION)

	def test_website_image_is_used_without_a_slideshow(self):
		item_code = self.make_plain_item()
		self.make_website_item(item_code, f"products/single-{self.suffix.lower()}")
		self.migrate([item_code])
		self.assertEqual([row.image for row in self.get_product(item_code).images], [self.website_image])

	def test_a_written_description_is_kept(self):
		frappe.db.set_value("Item", self.item_code, "description", "Written by the merchant")
		self.migrate([self.item_code])
		self.assertEqual(
			frappe.db.get_value("Item", self.item_code, "description"), "Written by the merchant"
		)

	def test_reviews_and_wishlist_move_to_the_product(self):
		counts = self.migrate([self.item_code])
		product = self.get_product(self.item_code)

		self.assertEqual((counts["reviews"], counts["wishlist_items"]), (1, 1))
		review = frappe.get_all(
			"Product Review",
			filters={"variant": product.name},
			fields=["owner", "rating", "review_title", "is_published", "item_style"],
		)
		self.assertEqual(
			[(row.owner, row.rating, row.review_title, row.is_published, row.item_style) for row in review],
			[(self.shopper, 4, "Lovely", 1, self.item_code)],
		)
		self.assertEqual((product.review_count, product.average_rating), (1, 4))
		self.assertTrue(
			frappe.db.exists("Commera Wishlist Item", {"user": self.shopper, "product": product.name})
		)

	def test_running_again_adds_nothing(self):
		self.migrate([self.item_code])
		product = self.get_product(self.item_code).name

		counts = apply_webshop_extras([self.item_code])

		self.assertEqual((counts["reviews"], counts["wishlist_items"]), (0, 0))
		self.assertEqual(frappe.db.count("Product Review", {"variant": product}), 1)
		self.assertEqual(frappe.db.count("Commera Wishlist Item", {"product": product}), 1)
		self.assertEqual(frappe.db.count("Website Slideshow Item", {"parent": product}), 2)

	def test_an_old_url_outside_products_redirects_to_the_product(self):
		item_code = self.make_plain_item()
		self.make_website_item(item_code, f"gadgets-{self.suffix.lower()}/lamp")
		self.migrate([item_code])

		self.assertEqual(self.get_product(item_code).route, f"gadgets-{self.suffix.lower()}/lamp")
		with self.assertRaises(frappe.Redirect):
			resolve_redirect(f"gadgets-{self.suffix.lower()}/lamp")
		self.assertEqual(frappe.flags.redirect_location, f"/products/gadgets-{self.suffix.lower()}/lamp")

	def test_offers_are_counted_as_dropped(self):
		self.website_item.append("offers", {"offer_title": "Free gift wrap"})
		self.website_item.save(ignore_permissions=True)
		self.assertEqual(self.migrate([self.item_code])["dropped_offers"], 1)

	def test_store_step_is_prefilled_from_webshop_settings(self):
		settings = frappe.get_single("Commera Settings")
		settings.company = settings.default_price_list = settings.ecommerce_warehouse = None
		frappe.db.set_single_value(
			"Webshop Settings", {"company": self.get_company(), "price_list": self.sale_price_list}
		)
		frappe.db.set_value("Website Item", {"published": 1}, "website_warehouse", self.warehouse)

		existing_store = get_existing_store(settings)

		self.assertEqual(existing_store["company"], self.get_company())
		self.assertEqual(existing_store["price_list"], self.sale_price_list)
		self.assertEqual(existing_store["warehouse"], self.warehouse)

	def get_company(self):
		return frappe.db.get_value("Warehouse", self.warehouse, "company")
