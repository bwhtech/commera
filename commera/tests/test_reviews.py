# Copyright (c) 2026, ivend and Contributors
# Tests for the storefront review endpoints (commera/api/reviews.py). Real-DB, auto-rolled-back.

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.reviews import get_reviews, submit_review, update_review
from commera.tests import get_test_configurator


class ReviewsTestCase(IntegrationTestCase):
	def setUp(self):
		self.suffix = frappe.generate_hash(length=8).upper()
		self.configurator = get_test_configurator()
		self.item_group = self.make_item_group()
		self.item_code = self.make_item()
		self.variant = self.make_variant()
		self.shopper = self.make_user("shopper")
		self.other_shopper = self.make_user("other")
		frappe.set_user(self.shopper)

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Reviews Group {self.suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		# commera makes the storefront display name mandatory on Item Group.
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def make_item(self):
		item = frappe.new_doc("Item")
		item.item_code = f"REVIEWS-{self.suffix}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.is_stock_item = 1
		item.insert()
		return item.name

	def make_variant(self):
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = self.configurator
		variant.item_style = self.item_code
		variant.item_group = self.item_group
		variant.attribute_value = f"Val {frappe.generate_hash(length=6)}"
		variant.display_name = f"Display {self.suffix}"
		variant.route = f"reviews-test-{self.suffix.lower()}"
		# images + sizes are required or validate() force-unpublishes the variant
		variant.append("images", {"image": "/assets/reviews-test.jpg"})
		variant.append("sizes", {"size": "M", "item_code": self.item_code})
		variant.is_published = 1
		variant.insert(ignore_permissions=True)
		return variant.name

	def make_user(self, label):
		user = frappe.new_doc("User")
		user.email = f"{label}-{self.suffix.lower()}@commera-tests.local"
		user.first_name = label.title()
		user.send_welcome_email = 0
		user.append_roles("Customer")
		user.insert(ignore_permissions=True)
		return user.name

	def make_review(self, rating=4, title="Good", comment="Nice product", published=False):
		name = submit_review(self.variant, rating, title, comment)
		if published:
			review = frappe.get_doc("Product Review", name)
			review.is_published = 1
			review.save(ignore_permissions=True)
		return name


class TestUpdateReview(ReviewsTestCase):
	def test_owner_can_edit_rating_title_and_comment(self):
		name = self.make_review()

		update_review(name, 2, "Fixed title", "Fixed comment")

		review = frappe.get_doc("Product Review", name)
		self.assertEqual(review.rating, 2)
		self.assertEqual(review.review_title, "Fixed title")
		self.assertEqual(review.comment, "Fixed comment")

	def test_another_shopper_cannot_edit_someone_elses_review(self):
		name = self.make_review(comment="Original comment")

		frappe.set_user(self.other_shopper)
		with self.assertRaises(frappe.ValidationError):
			update_review(name, 1, "Hijacked", "Hijacked comment")

		self.assertEqual(frappe.db.get_value("Product Review", name, "comment"), "Original comment")

	def test_guest_cannot_edit(self):
		name = self.make_review()

		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			update_review(name, 1, "Guest edit", "Guest comment")

	def test_unknown_review_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			update_review("does-not-exist", 3, "Title", "Comment")

	def test_rating_outside_one_to_five_is_rejected(self):
		name = self.make_review()

		with self.assertRaises(frappe.ValidationError):
			update_review(name, 6, "Title", "Comment")

	def test_over_long_comment_is_rejected(self):
		name = self.make_review()

		with self.assertRaises(frappe.ValidationError):
			update_review(name, 3, "Title", "x" * 2001)

	def test_title_is_capped_not_rejected(self):
		name = self.make_review()

		update_review(name, 3, "t" * 200, "Comment")

		self.assertEqual(len(frappe.db.get_value("Product Review", name, "review_title")), 140)

	def test_editing_a_published_review_sends_it_back_to_moderation(self):
		name = self.make_review(rating=5, published=True)
		self.assertEqual(frappe.db.get_value("Style Attribute Variant", self.variant, "review_count"), 1)

		update_review(name, 1, "Rewritten", "Rewritten comment")

		self.assertEqual(frappe.db.get_value("Product Review", name, "is_published"), 0)
		variant = frappe.db.get_value(
			"Style Attribute Variant", self.variant, ["average_rating", "review_count"], as_dict=True
		)
		self.assertEqual(variant.review_count, 0)
		self.assertEqual(variant.average_rating, 0)

	def test_verified_purchase_evidence_is_frozen(self):
		name = self.make_review()
		frappe.db.set_value(
			"Product Review", name, {"verified_purchase": 1, "purchased_item": self.item_code}
		)

		update_review(name, 3, "Edited", "Edited comment")

		review = frappe.db.get_value(
			"Product Review", name, ["verified_purchase", "purchased_item"], as_dict=True
		)
		self.assertEqual(review.verified_purchase, 1)
		self.assertEqual(review.purchased_item, self.item_code)

	def test_the_edit_returns_the_refreshed_storefront_payload(self):
		name = self.make_review(rating=5, published=True)

		payload = update_review(name, 2, "Rewritten", "Rewritten comment")

		self.assertEqual(payload["reviews"], [])
		self.assertEqual(payload["review_count"], 0)
		self.assertEqual(payload["my_review"]["name"], name)
		self.assertEqual(payload["my_review"]["rating"], 2)
		self.assertFalse(payload["my_review"]["is_published"])


class TestGetReviewsOwnReview(ReviewsTestCase):
	def test_own_unpublished_review_is_returned_to_its_author(self):
		name = self.make_review(rating=4, title="Mine", comment="My comment")

		payload = get_reviews(self.variant)

		self.assertEqual(payload["my_review"]["name"], name)
		self.assertEqual(payload["my_review"]["rating"], 4)
		self.assertEqual(payload["my_review"]["review_title"], "Mine")
		self.assertEqual(payload["my_review"]["comment"], "My comment")
		self.assertTrue(payload["has_reviewed"])
		self.assertFalse(payload["can_review"])

	def test_another_shopper_never_sees_my_review_as_theirs(self):
		self.make_review()

		frappe.set_user(self.other_shopper)
		payload = get_reviews(self.variant)

		self.assertIsNone(payload["my_review"])
		self.assertTrue(payload["can_review"])

	def test_guest_gets_no_own_review(self):
		self.make_review()

		frappe.set_user("Guest")
		payload = get_reviews(self.variant)

		self.assertIsNone(payload["my_review"])
		self.assertFalse(payload["can_review"])


class TestQueuedRecomputes(IntegrationTestCase):
	"""Both run after commit, where an error would fail a saved change and skip the other callbacks."""

	def test_a_full_queue_is_logged_not_raised(self):
		from commera.commera_ecommerce.doctype.product_review.product_review import queue_variant_rating
		from commera.utils import queue_ecommerce_status_update

		with (
			patch("frappe.enqueue", side_effect=Exception("queue full")),
			patch("frappe.log_error") as log_error,
		):
			queue_variant_rating("ZZ-VARIANT")
			queue_ecommerce_status_update("ZZ-ORDER")

		self.assertEqual(log_error.call_count, 2)
