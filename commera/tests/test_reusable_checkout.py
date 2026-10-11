from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from commera.api.payments import get_checkout_payment_methods, get_reusable_checkout_url, open_checkout
from commera.jobs import delete_old_draft_quotations

GATEWAY = "Test Wallet"


def make_quotation(amount=20):
	return SimpleNamespace(
		name="WALLET-CART-1",
		currency="USD",
		rounded_total=amount,
		grand_total=amount,
		custom_delivery_option=None,
		flags=frappe._dict(),
	)


class TestReusableCheckout(UnitTestCase):
	def test_checkout_offers_gateways_for_the_cart_currency(self):
		with (
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=[GATEWAY]) as available,
			patch("commera.api.payments.frappe.get_cached_value", return_value=0),
			patch(
				"commera.api.payments.filter_payment_methods",
				side_effect=lambda quotation, methods, strict: methods,
			),
		):
			payment_methods = get_checkout_payment_methods(make_quotation())

		available.assert_called_once_with("USD")
		self.assertEqual(payment_methods, [GATEWAY])

	def test_an_unsupported_currency_is_rejected_before_a_payment_request_is_created(self):
		quotation = make_quotation()
		with (
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=[]) as available,
			patch("commera.api.payments.resolve_payment_mode", return_value=GATEWAY),
			patch("commera.api.payments.get_reusable_checkout_gateways", return_value=[GATEWAY]),
			patch("commera.api.payments.validate_cart_is_not_in_checkout"),
			patch("commera.api.payments.update_delivery_charges"),
			patch("commera.api.payments.validate_cart"),
			patch("commera.api.payments.validate_expected_total"),
			patch("commera.api.payments.get_checkout_payment_methods", return_value=[]),
			patch("commera.api.payments._", side_effect=lambda message: message),
			patch("commera.api.payments.refuse_payment", side_effect=frappe.ValidationError),
			patch("commera.api.payments.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				open_checkout(quotation, GATEWAY)

		available.assert_called_with("USD")
		get_doc.assert_not_called()

	def test_a_repeat_checkout_reuses_the_open_link_of_a_reusable_gateway(self):
		quotation = make_quotation()
		with (
			patch("commera.api.payments.resolve_payment_mode", return_value=GATEWAY),
			patch("commera.api.payments.get_reusable_checkout_gateways", return_value=[GATEWAY]),
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=[GATEWAY]),
			patch("commera.api.payments.get_reusable_checkout_url", return_value="https://wallet.test/old"),
			patch("commera.api.payments.validate_cart_is_not_in_checkout") as validate_cart,
			patch("commera.api.payments.frappe.get_doc") as get_doc,
		):
			result = open_checkout(quotation, GATEWAY)

		self.assertEqual(result, {"order_url": "https://wallet.test/old"})
		validate_cart.assert_not_called()
		get_doc.assert_not_called()

	def test_a_changed_cart_cannot_reuse_its_old_link(self):
		quotation = make_quotation(amount=30)
		payment_request = SimpleNamespace(
			status="Pending",
			gateway=GATEWAY,
			currency_code="USD",
			amount=20,
			order_url="https://wallet.test/old",
			sync_status=Mock(),
		)
		with (
			patch("commera.api.payments.get_open_gateway_payment_request", return_value="GPR-1"),
			patch("commera.api.payments.frappe.get_doc", return_value=payment_request),
			patch(
				"commera.api.payments.to_minor_units", side_effect=lambda amount, currency: int(amount * 100)
			),
		):
			self.assertIsNone(get_reusable_checkout_url(quotation, GATEWAY, GATEWAY, None))

		payment_request.sync_status.assert_called_once_with()

	def test_a_reused_link_must_match_the_total_the_shopper_saw(self):
		quotation = make_quotation()
		payment_request = SimpleNamespace(
			status="Pending",
			gateway=GATEWAY,
			currency_code="USD",
			amount=20,
			order_url="https://wallet.test/old",
			sync_status=Mock(),
		)
		with (
			patch("commera.api.payments.get_open_gateway_payment_request", return_value="GPR-1"),
			patch("commera.api.payments.frappe.get_doc", return_value=payment_request),
			patch(
				"commera.api.payments.to_minor_units", side_effect=lambda amount, currency: int(amount * 100)
			),
			patch(
				"commera.api.payments.validate_expected_total", side_effect=frappe.ValidationError
			) as validate,
		):
			with self.assertRaises(frappe.ValidationError):
				get_reusable_checkout_url(quotation, GATEWAY, GATEWAY, 25)

		validate.assert_called_once_with(quotation, GATEWAY, 25)

	def test_a_paid_request_goes_to_confirmation(self):
		quotation = make_quotation()
		payment_request = SimpleNamespace(name="GPR-1", status="Pending", gateway=GATEWAY)

		def mark_paid():
			payment_request.status = "Paid"

		payment_request.sync_status = mark_paid
		with (
			patch("commera.api.payments.get_open_gateway_payment_request", return_value="GPR-1"),
			patch("commera.api.payments.frappe.get_doc", return_value=payment_request),
			patch(
				"commera.api.payments.get_confirmation_url", return_value="/orders/confirmation"
			) as confirm,
		):
			self.assertEqual(
				get_reusable_checkout_url(quotation, GATEWAY, GATEWAY, None), "/orders/confirmation"
			)

		confirm.assert_called_once_with("GPR-1")

	def test_cleanup_keeps_a_cart_with_a_pending_reusable_checkout(self):
		exists = Mock(return_value=True)
		delete_doc = Mock()
		fake_frappe = SimpleNamespace(
			get_all=Mock(return_value=["WALLET-CART-1"]),
			db=SimpleNamespace(exists=exists),
			delete_doc=delete_doc,
		)
		with (
			patch("commera.jobs.frappe", fake_frappe),
			patch("commera.jobs.now_datetime", return_value=datetime(2026, 9, 24)),
			patch("commera.jobs.get_reusable_checkout_gateways", return_value=[GATEWAY]),
		):
			delete_old_draft_quotations()

		exists.assert_called_once_with(
			"Gateway Payment Request",
			{
				"ref_doctype": "Quotation",
				"ref_docname": "WALLET-CART-1",
				"gateway": ["in", [GATEWAY]],
				"status": "Pending",
			},
		)
		delete_doc.assert_not_called()

	def test_cleanup_deletes_a_stale_cart_when_no_gateway_keeps_checkouts_open(self):
		delete_doc = Mock()
		fake_frappe = SimpleNamespace(
			get_all=Mock(return_value=["WALLET-CART-1"]),
			db=SimpleNamespace(exists=Mock(return_value=True)),
			delete_doc=delete_doc,
		)
		with (
			patch("commera.jobs.frappe", fake_frappe),
			patch("commera.jobs.now_datetime", return_value=datetime(2026, 9, 24)),
			patch("commera.jobs.get_reusable_checkout_gateways", return_value=[]),
		):
			delete_old_draft_quotations()

		delete_doc.assert_called_once_with("Quotation", "WALLET-CART-1")

	def test_a_gateway_without_the_capability_never_reuses_a_link(self):
		quotation = make_quotation()
		with (
			patch("commera.api.payments.resolve_payment_mode", return_value=GATEWAY),
			patch("commera.api.payments.get_reusable_checkout_gateways", return_value=[]),
			patch("commera.api.payments.get_payment_modes_for_currency", return_value=[GATEWAY]),
			patch("commera.api.payments.get_reusable_checkout_url") as reuse,
			patch("commera.api.payments.validate_cart_is_not_in_checkout", side_effect=StopIteration),
		):
			with self.assertRaises(StopIteration):
				open_checkout(quotation, GATEWAY)

		reuse.assert_not_called()
