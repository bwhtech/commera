from types import SimpleNamespace
from unittest.mock import patch

import frappe
import jwt
import requests
from frappe.tests import IntegrationTestCase

from commera.cloud import link
from commera.cloud.client import SITE_KEY_HEADER, call_cloud, is_linked

SERVER_URL = "https://cloud.example.test"
SITE = "shop.example.test"
RENAMED_SITE = "renamed.example.test"
LINK = {"site": SITE, "team": "Acme", "site_key": "cck_one.secret"}


def clear_attempts():
	for site in (SITE, RENAMED_SITE):
		frappe.cache.delete_value(f"{link.ATTEMPTED_CACHE_KEY}:{site}")


class CloudLinkTestCase(IntegrationTestCase):
	"""A Frappe Cloud site that tests against its own Commera Cloud, with no link yet."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(clear_attempts)
		clear_attempts()
		settings = frappe.get_single("Commera Cloud Settings")
		settings.update({"server_url": None, "site": None, "team": None, "site_key": None, "linked_on": None})
		settings.save()

		self.enterContext(
			patch.dict(
				frappe.conf,
				{
					link.SERVER_URL_CONFIG_KEY: SERVER_URL + "/",
					"pilot_endpoint": "https://pilot.example.test",
					"pilot_auth_token": "token",
				},
			)
		)
		self.site_name = self.enterContext(patch("commera.cloud.link.get_site_name", return_value=SITE))
		self.exchange = self.enterContext(
			patch(
				"commera.cloud.link.exchange_identity_token", side_effect=lambda server_url, site: dict(LINK)
			)
		)


class TestLinkSite(CloudLinkTestCase):
	def test_a_new_site_saves_its_key(self):
		link.link_site()

		settings = frappe.get_single("Commera Cloud Settings")
		self.exchange.assert_called_once_with(SERVER_URL, SITE)
		self.assertEqual((settings.server_url, settings.site, settings.team), (SERVER_URL, SITE, "Acme"))
		self.assertEqual(settings.site_key_value, "cck_one.secret")
		self.assertTrue(is_linked())

	def test_a_linked_site_is_not_pending(self):
		self.assertTrue(link.is_link_pending())
		link.link_site()
		clear_attempts()

		self.assertFalse(link.is_link_pending())

	def test_a_renamed_site_links_again_at_once(self):
		link.link_site()
		self.site_name.return_value = RENAMED_SITE

		self.assertTrue(link.is_link_pending())

	def test_a_new_server_url_links_again(self):
		link.link_site()
		clear_attempts()

		with patch.dict(frappe.conf, {link.SERVER_URL_CONFIG_KEY: "https://other.example.test"}):
			self.assertTrue(link.is_link_pending())

	def test_a_failed_link_is_retried_after_an_hour(self):
		self.exchange.side_effect = requests.ConnectionError("Unavailable")
		with self.assertRaises(requests.ConnectionError):
			link.link_site()

		self.assertFalse(link.is_link_pending())
		clear_attempts()
		self.assertTrue(link.is_link_pending())

	def test_a_site_without_a_server_url_links_to_the_default_one(self):
		with patch.dict(frappe.conf, {link.SERVER_URL_CONFIG_KEY: None}):
			link.link_site()

		self.exchange.assert_called_once_with(link.DEFAULT_SERVER_URL, SITE)
		self.assertEqual(frappe.get_single("Commera Cloud Settings").server_url, link.DEFAULT_SERVER_URL)

	def test_a_site_off_frappe_cloud_is_left_alone(self):
		with (
			patch.dict(frappe.conf, {"pilot_endpoint": None}),
			patch("commera.cloud.link.frappe.enqueue") as enqueue,
		):
			self.assertFalse(link.is_link_pending())
			link.queue_link_if_pending()
			link.link_site()

		enqueue.assert_not_called()
		self.exchange.assert_not_called()

	def test_the_hourly_check_queues_one_deduplicated_job(self):
		with patch("commera.cloud.link.frappe.enqueue") as enqueue:
			link.queue_link_if_pending()

		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["job_id"], "commera-cloud-link")
		self.assertTrue(enqueue.call_args.kwargs["deduplicate"])


class TestRegistrationSiteName(IntegrationTestCase):
	def token(self, hosts):
		return jwt.encode({"hosts": hosts}, "unverified-test-signing-secret-32b", algorithm="HS256")

	def test_a_placeholder_hostname_uses_a_listed_one_on_a_single_site_bench(self):
		with patch("commera.cloud.link.get_sites", return_value=["site-1234.example.test"]):
			name = link.get_registration_site_name(
				self.token(["site-1234.f.cloud", SITE, RENAMED_SITE]), "site-1234.example.test"
			)

		self.assertEqual(name, SITE)

	def test_a_listed_hostname_is_kept(self):
		with patch("commera.cloud.link.get_sites", return_value=[SITE]):
			self.assertEqual(link.get_registration_site_name(self.token([SITE, RENAMED_SITE]), SITE), SITE)

	def test_a_multi_site_bench_keeps_its_own_hostname(self):
		with patch("commera.cloud.link.get_sites", return_value=[SITE, RENAMED_SITE]):
			self.assertEqual(link.get_registration_site_name(self.token([RENAMED_SITE]), SITE), SITE)


class TestCallCloud(CloudLinkTestCase):
	def respond(self, status_code: int, message=None):
		response = requests.Response()
		response.status_code = status_code
		response._content = frappe.as_json({"message": message}).encode()
		return patch("commera.cloud.client.requests.post", return_value=response)

	def test_a_call_sends_the_site_key(self):
		link.link_site()

		with self.respond(200, {"site": SITE}) as post:
			self.assertEqual(call_cloud("commera_cloud.api.site.get_site_details"), {"site": SITE})

		self.assertEqual(
			post.call_args.args[0], f"{SERVER_URL}/api/method/commera_cloud.api.site.get_site_details"
		)
		self.assertEqual(post.call_args.kwargs["headers"], {SITE_KEY_HEADER: "cck_one.secret"})

	def test_a_refused_key_links_again_at_most_once_an_hour(self):
		link.link_site()
		with patch("commera.cloud.link.frappe.enqueue") as enqueue, self.respond(401):
			with self.assertRaises(requests.HTTPError):
				call_cloud("commera_cloud.api.site.get_site_details")
			enqueue.assert_not_called()

			clear_attempts()
			with self.assertRaises(requests.HTTPError):
				call_cloud("commera_cloud.api.site.get_site_details")
			enqueue.assert_called_once()

	def test_an_unlinked_site_cannot_call(self):
		self.assertFalse(is_linked())
		with self.assertRaises(frappe.ValidationError):
			call_cloud("commera_cloud.api.site.get_site_details")
