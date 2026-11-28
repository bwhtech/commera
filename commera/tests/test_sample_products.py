# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe

from commera.api.admin.catalog import get_product_chain
from commera.api.admin.sample_products import (
	SAMPLE_COLLECTION,
	SAMPLE_FLAG,
	SAMPLE_PRODUCTS,
	get_sample_product_names,
	load_sample_products,
	remove_sample_products,
)
from commera.install_fashion_demo_data import FASHION_PRODUCTS
from commera.tests.test_product_onboarding import ProductOnboardingTestCase

SAMPLE_TITLES = {
	product["name"]
	for product in FASHION_PRODUCTS
	if product["code"] in {sample["code"] for sample in SAMPLE_PRODUCTS}
}


class TestSampleProducts(ProductOnboardingTestCase):
	def setUp(self):
		frappe.db.savepoint("sample_products_test")
		super().setUp()
		self.assertFalse(get_sample_product_names(), "the site already carries sample products")

	def tearDown(self):
		frappe.db.rollback(save_point="sample_products_test")
		super().tearDown()

	def test_load_creates_published_flagged_products_with_photos(self):
		created = load_sample_products()["created"]

		self.assertEqual({row["title"] for row in created}, SAMPLE_TITLES)
		self.assertEqual(set(get_sample_product_names()), {row["item_template"] for row in created})
		for row in created:
			chain = get_product_chain(row["item_template"])
			variants = frappe.get_all(
				"Style Attribute Variant",
				filters={"name": ["in", chain["variants"]]},
				fields=["name", "is_published"],
			)
			self.assertTrue(all(variant.is_published for variant in variants), row["title"])
			self.assertTrue(
				frappe.db.exists(
					"Website Slideshow Item",
					{"parent": ["in", chain["variants"]], "image": ["like", "/assets/%"]},
				)
			)
			self.assertFalse(
				frappe.db.exists("Item", {"name": ["in", chain["item_codes"]], SAMPLE_FLAG: 1}),
				"only the product carries the flag, never its sizes",
			)

		cardigan = next(row for row in created if row["title"] == "Cozy Knit Cardigan Sweater")
		self.assertEqual(len(get_product_chain(cardigan["item_template"])["item_codes"]), 6)

	def test_a_second_load_is_refused(self):
		load_sample_products()
		with self.assertRaises(frappe.ValidationError):
			load_sample_products()

	def test_remove_deletes_only_the_samples(self):
		load_sample_products()

		result = remove_sample_products()

		self.assertEqual(len(result["removed"]), len(SAMPLE_PRODUCTS))
		self.assertFalse(result["kept"])
		self.assertFalse(get_sample_product_names())
		self.assertFalse(frappe.db.exists("Item Group", SAMPLE_COLLECTION))
		self.assertTrue(frappe.db.exists("Item", self.item_template))
