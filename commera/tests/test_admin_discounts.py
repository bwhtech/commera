from unittest.mock import patch

import frappe
from frappe.utils.data import add_days, today

from commera.api.admin import discounts as admin_discounts
from commera.discounts.codes import MAX_CODES_IN_REQUEST, generate_codes
from commera.tests.test_discount_codes import SHIRT_RATE, DiscountCodeTestCase


class TestAdminDiscounts(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(self.set_sale_price_list, sale_price_list)
		self.set_sale_price_list(self.price_list)

	def set_sale_price_list(self, price_list: str):
		frappe.db.set_single_value("Commera Settings", "sale_price_list", price_list)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def save(self, **values) -> dict:
		draft = {
			"method": "Code",
			"discount_type": "Amount Off Order",
			"value_type": "Percentage",
			"value": 10,
			"code": f"zz{frappe.generate_hash(length=6)}",
			**values,
		}
		return admin_discounts.save_discount(draft)

	def test_a_code_discount_is_created_with_its_code_as_title(self):
		saved = self.save(code="zz-welcome")

		self.assertEqual(
			(saved["code"], saved["title"], saved["status"]), ("ZZ-WELCOME", "ZZ-WELCOME", "Active")
		)
		self.assertEqual(saved["discount_class"], "Order")

	def test_changing_an_unused_code_replaces_it(self):
		saved = self.save(code="zz-first")

		updated = admin_discounts.save_discount({**saved, "code": "zz-second"})

		self.assertEqual(updated["code"], "ZZ-SECOND")
		self.assertFalse(frappe.db.exists("Commera Discount Code", "ZZ-FIRST"))

	def test_specific_customers_are_saved_and_read_back_with_their_names(self):
		saved = self.save(eligibility="Specific Customers", customers=[{"customer": self.customer.name}])

		self.assertEqual(
			saved["customers"],
			[{"customer": self.customer.name, "customer_name": self.customer.customer_name}],
		)

	def test_the_list_filters_by_tab_and_finds_by_code(self):
		scheduled = self.save(starts_on=add_days(today(), 5))
		active = self.save(code="zz-findme")

		scheduled_names = [row["name"] for row in admin_discounts.get_discounts("scheduled")["discounts"]]
		found = admin_discounts.get_discounts(search="ZZ-FINDME")["discounts"]

		self.assertIn(scheduled["name"], scheduled_names)
		self.assertNotIn(active["name"], scheduled_names)
		self.assertEqual([row["name"] for row in found], [active["name"]])

	def test_the_list_carries_what_its_summary_reads(self):
		saved = self.save(
			discount_type="Amount Off Order", tiered=1, tiers=[{"minimum_subtotal": 100, "value": 5}]
		)

		row = next(
			row for row in admin_discounts.get_discounts()["discounts"] if row["name"] == saved["name"]
		)

		self.assertEqual(row["tiers"], [{"minimum_subtotal": 100, "value": 5}])
		self.assertEqual(row["combines_with_shipping"], 1)

	def test_generated_codes_download_as_csv(self):
		saved = self.save()

		admin_discounts.create_codes(saved["name"], 3, "zz-")
		admin_discounts.download_codes(saved["name"])

		self.assertEqual(admin_discounts.get_discount(saved["name"])["generated_codes"], 3)
		self.assertEqual(frappe.response["filecontent"].count("\n"), 4)

	def test_a_used_discount_cannot_be_deleted(self):
		saved = self.save()
		self.place_order(self.create_quotation({self.shirt: 1}, (saved["code"],)))

		with self.assertRaises(frappe.ValidationError):
			admin_discounts.delete_discount(saved["name"])

	def test_a_code_discount_needs_a_code(self):
		with self.assertRaisesRegex(frappe.ValidationError, "needs a code"):
			self.save(code=None)

	def test_deleting_a_discount_deletes_its_codes(self):
		saved = self.save(code="zz-gone")

		admin_discounts.delete_discount(saved["name"])

		self.assertFalse(frappe.db.exists("Commera Discount", saved["name"]))
		self.assertFalse(frappe.db.exists("Commera Discount Code", "ZZ-GONE"))

	def test_a_large_batch_of_codes_is_made_in_the_background(self):
		saved = self.save()
		jobs = []
		with patch.object(frappe, "enqueue", side_effect=lambda method, **kwargs: jobs.append(kwargs)):
			response = admin_discounts.create_codes(saved["name"], MAX_CODES_IN_REQUEST + 1, "zz-")

		self.assertEqual(response, {"created": 0, "queued": MAX_CODES_IN_REQUEST + 1})
		self.assertEqual(jobs[0]["count"], MAX_CODES_IN_REQUEST + 1)
		self.assertEqual(admin_discounts.get_discount(saved["name"])["generated_codes"], 0)

		generate_codes(**{key: jobs[0][key] for key in ("discount", "count", "prefix")})
		self.assertEqual(
			admin_discounts.get_discount(saved["name"])["generated_codes"], MAX_CODES_IN_REQUEST + 1
		)

	def test_the_list_carries_each_discounts_currency(self):
		saved = self.save(currency=self.currency)

		row = next(
			row for row in admin_discounts.get_discounts()["discounts"] if row["name"] == saved["name"]
		)

		self.assertEqual(row["currency"], self.currency)

	def test_the_test_cart_prices_an_unsaved_draft(self):
		draft = {
			"discount_type": "Amount Off Order",
			"value_type": "Percentage",
			"value": 10,
			"payment_condition": "Prepaid",
		}

		prepaid = admin_discounts.test_discount(draft, [{"item_code": self.shirt, "qty": 2}])
		cod = admin_discounts.test_discount(draft, [{"item_code": self.shirt, "qty": 2}], payment_kind="cod")

		self.assertEqual((prepaid["subtotal"], prepaid["discount"]), (2 * SHIRT_RATE, 18))
		self.assertEqual(cod["discount"], 0)
		self.assertEqual(len(cod["reasons"]), 1)

	def test_target_search_finds_products(self):
		matches = admin_discounts.search_targets("Item", self.shirt)

		self.assertEqual([match["value"] for match in matches], [self.shirt])

	def test_a_code_already_in_use_is_refused_in_any_case(self):
		self.save(code="zz-taken")

		with self.assertRaises(frappe.DuplicateEntryError):
			self.save(code="ZZ-Taken")

	def test_an_end_date_before_the_start_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.save(starts_on=add_days(today(), 5), ends_on=add_days(today(), 1))

	def test_a_percentage_over_100_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.save(value=150)

	def test_search_finds_a_discount_by_one_of_its_generated_codes(self):
		saved = self.save()
		admin_discounts.create_codes(saved["name"], 2, "zz-gen-")
		generated = frappe.get_all(
			"Commera Discount Code", {"discount": saved["name"], "is_generated": 1}, pluck="name", limit=1
		)[0]

		found = admin_discounts.get_discounts(search=generated.lower())["discounts"]

		self.assertEqual([row["name"] for row in found], [saved["name"]])

	def test_a_guest_cannot_create_codes(self):
		saved = self.save()
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			admin_discounts.create_codes(saved["name"], 5, "zz-")

	def test_the_test_cart_says_how_much_more_to_spend(self):
		draft = {
			"discount_type": "Amount Off Order",
			"value_type": "Percentage",
			"value": 10,
			"minimum_requirement": "Subtotal",
			"minimum_subtotal": 500,
		}

		result = admin_discounts.test_discount(draft, [{"item_code": self.shirt, "qty": 1}])

		self.assertEqual(result["discount"], 0)
		[reason] = result["reasons"]
		self.assertIn("410", reason)
		self.assertIn("more to use", reason)
