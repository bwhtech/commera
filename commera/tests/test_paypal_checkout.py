from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from commera.api.payments import get_reusable_paypal_url, open_checkout
from commera.jobs import delete_old_draft_quotations
from commera.www.cart.checkout import get_context


def make_quotation(amount=20):
	return SimpleNamespace(name="PAYPAL-CART-1", currency="USD", rounded_total=amount, grand_total=amount)


class TestPayPalCheckout(UnitTestCase):
	def test_checkout_offers_gateways_for_the_cart_currency(self):
		quotation = SimpleNamespace(currency="USD", items=[object()])
		context = frappe._dict()
		with (
			patch("commera.www.cart.checkout._get_cart_quotation", return_value=quotation),
			patch("commera.www.cart.checkout.frappe.get_cached_doc") as get_settings,
			patch(
				"commera.www.cart.checkout.get_payment_modes_for_currency", return_value=["PayPal"]
			) as available,
			patch("commera.www.cart.checkout.get_coupon_code", side_effect=StopIteration),
		):
			get_settings.return_value.get.return_value = None
			with self.assertRaises(StopIteration):
				get_context(context)

		available.assert_called_once_with("USD")
		self.assertEqual(context.payment_gateways, ["PayPal"])

	def test_an_unsupported_currency_is_rejected_before_a_payment_request_is_created(self):
		quotation = make_quotation()
		with (
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=[]) as available,
			patch("commera.api.payments.resolve_payment_mode", return_value="PayPal"),
			patch("commera.api.payments.validate_cart_is_not_in_checkout"),
			patch("commera.api.payments.update_delivery_charges"),
			patch("commera.api.payments._", side_effect=lambda message: message),
			patch("commera.api.payments.refuse_payment", side_effect=frappe.ValidationError),
			patch("commera.api.payments.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				open_checkout(quotation, "PayPal")

		available.assert_called_with("USD")
		get_doc.assert_not_called()

	def test_a_repeat_checkout_uses_the_existing_paypal_url(self):
		quotation = make_quotation()
		with (
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=["PayPal"]),
			patch("commera.api.payments.get_reusable_paypal_url", return_value="https://paypal.test/old"),
			patch("commera.api.payments.validate_cart_is_not_in_checkout") as validate_cart,
			patch("commera.api.payments.frappe.get_doc") as get_doc,
		):
			result = open_checkout(quotation, "PayPal")

		self.assertEqual(result, {"order_url": "https://paypal.test/old"})
		validate_cart.assert_not_called()
		get_doc.assert_not_called()

	def test_a_changed_cart_cannot_reuse_its_old_paypal_url(self):
		quotation = make_quotation(amount=30)
		payment_request = SimpleNamespace(
			status="Pending",
			gateway="PayPal",
			currency_code="USD",
			amount=20,
			order_url="https://paypal.test/old",
			sync_status=Mock(),
		)
		with (
			patch("commera.api.payments.get_open_gateway_payment_request", return_value="GPR-1"),
			patch("commera.api.payments.frappe.get_doc", return_value=payment_request),
			patch("commera.api.payments.to_minor_units", side_effect=lambda amount, currency: int(amount * 100)),
		):
			self.assertIsNone(get_reusable_paypal_url(quotation))

		payment_request.sync_status.assert_called_once_with()

	def test_a_paid_paypal_request_goes_to_confirmation(self):
		quotation = make_quotation()
		payment_request = SimpleNamespace(name="GPR-1", status="Pending", gateway="PayPal")

		def mark_paid():
			payment_request.status = "Paid"

		payment_request.sync_status = mark_paid
		with (
			patch("commera.api.payments.get_open_gateway_payment_request", return_value="GPR-1"),
			patch("commera.api.payments.frappe.get_doc", return_value=payment_request),
			patch("commera.api.payments.get_confirmation_url", return_value="/orders/confirmation") as confirm,
		):
			self.assertEqual(get_reusable_paypal_url(quotation), "/orders/confirmation")

		confirm.assert_called_once_with("GPR-1")

	def test_cleanup_keeps_a_cart_with_pending_paypal_payment(self):
		exists = Mock(return_value=True)
		delete_doc = Mock()
		fake_frappe = SimpleNamespace(
			get_all=Mock(return_value=["PAYPAL-CART-1"]),
			db=SimpleNamespace(exists=exists),
			delete_doc=delete_doc,
		)
		with (
			patch("commera.jobs.frappe", fake_frappe),
			patch("commera.jobs.now_datetime", return_value=datetime(2026, 9, 24)),
		):
			delete_old_draft_quotations()

		exists.assert_called_once_with(
			"Gateway Payment Request",
			{
				"ref_doctype": "Quotation",
				"ref_docname": "PAYPAL-CART-1",
				"gateway": "PayPal",
				"status": "Pending",
			},
		)
		delete_doc.assert_not_called()
