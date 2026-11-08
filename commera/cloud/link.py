from urllib.parse import urlparse

import frappe
import jwt
import requests
from frappe.integrations.frappe_providers.cloud_settings import PilotClient, is_v2_site
from frappe.utils import get_sites, get_url, now_datetime
from redis.exceptions import ConnectionError as RedisConnectionError

DEFAULT_SERVER_URL = "https://cloud.commera.app"
# Only for testing against another Commera Cloud. Set it in the site config.
SERVER_URL_CONFIG_KEY = "commera_cloud_url"
ATTEMPTED_CACHE_KEY = "commera_cloud_link_attempted"
ATTEMPT_INTERVAL_SECONDS = 60 * 60
EXCHANGE_METHOD = "commera_cloud.api.frappe_cloud.exchange_frappe_cloud_token"


def get_server_url() -> str:
	return (frappe.conf.get(SERVER_URL_CONFIG_KEY) or DEFAULT_SERVER_URL).rstrip("/")


def is_on_frappe_cloud() -> bool:
	"""Pilot can ask Frappe Cloud for this site's identity token. Other sites link from the browser later."""
	return is_v2_site()


def get_site_name() -> str:
	return urlparse(get_url()).hostname


def has_recent_attempt() -> bool:
	"""A link attempt for the current hostname ran within the hour. A renamed site tries at once."""
	return bool(frappe.cache.get_value(f"{ATTEMPTED_CACHE_KEY}:{get_site_name()}"))


def is_link_pending() -> bool:
	"""No key yet, or the server or hostname changed since the last link, and no recent attempt."""
	if not is_on_frappe_cloud() or has_recent_attempt():
		return False
	settings = frappe.get_single("Commera Cloud Settings")
	return (
		not settings.site_key_value
		or settings.server_url != get_server_url()
		or (settings.linked_hostname or settings.site) != get_site_name()
	)


def queue_link(after_commit: bool = False) -> None:
	"""Runs in the background, so installs and setup do not wait for Commera Cloud."""
	if not is_on_frappe_cloud():
		return
	try:
		frappe.enqueue(
			"commera.cloud.link.link_site",
			queue="short",
			job_id="commera-cloud-link",
			deduplicate=True,
			enqueue_after_commit=after_commit,
		)
	except RedisConnectionError:
		# The hourly check tries again, so a queue outage must not fail an install.
		frappe.logger("commera").warning("Could not queue the Commera Cloud link", exc_info=True)


def queue_initial_link(*args) -> None:
	"""Install and setup must commit their records before the worker reads them."""
	queue_link(after_commit=True)


def queue_link_if_pending() -> None:
	if is_link_pending():
		queue_link()


def retry_after_refusal() -> None:
	"""Commera Cloud refused the key, for example after another link revoked it. Link again, at most once an hour."""
	if is_on_frappe_cloud() and not has_recent_attempt():
		queue_link()


def link_site() -> None:
	"""Exchange a Frappe Cloud team identity token for this site's Commera Cloud key, and save it."""
	if not is_on_frappe_cloud():
		return

	server_url = get_server_url()
	site_name = get_site_name()
	try:
		save_link(server_url, exchange_identity_token(server_url, site_name), site_name)
	finally:
		frappe.cache.set_value(
			f"{ATTEMPTED_CACHE_KEY}:{site_name}", 1, expires_in_sec=ATTEMPT_INTERVAL_SECONDS
		)


def exchange_identity_token(server_url: str, site_name: str) -> dict:
	client = PilotClient()
	identity = client.post(
		client.site_path("central/central.api.pilot.get_team_identity_token"), {"audience": server_url}
	)
	response = requests.post(
		f"{server_url}/api/method/{EXCHANGE_METHOD}",
		json={
			"token": identity["token"],
			"site_name": get_registration_site_name(identity["token"], site_name),
		},
		timeout=15,
		allow_redirects=False,
	)
	response.raise_for_status()
	return response.json()["message"]


def get_registration_site_name(token: str, site_name: str) -> str:
	"""A new Frappe Cloud site can still answer to a placeholder hostname. On a single-site bench, use one
	that the token lists instead. The pick is stable, so a retry links the same hostname."""
	if len(get_sites()) != 1:
		return site_name

	# Commera Cloud verifies the token. Only its hosts are read here.
	hosts = jwt.decode(token, options={"verify_signature": False}).get("hosts", [])
	if not hosts or site_name in hosts:
		return site_name

	preferred_hosts = [host for host in hosts if not host.startswith("site-")]
	return (preferred_hosts or hosts)[0]


def save_link(server_url: str, link: dict, linked_hostname: str | None = None) -> None:
	"""`site` is the name Commera Cloud registered, which can be a host from the token. The check for a
	renamed site compares `linked_hostname`, the name this site answered to, so it does not re-link hourly."""
	settings = frappe.get_single("Commera Cloud Settings")
	settings.update(
		{
			"server_url": server_url,
			"site": link["site"],
			"linked_hostname": linked_hostname or link["site"],
			"team": link["team"],
			"site_key": link["site_key"],
			"linked_on": now_datetime(),
		}
	)
	# A background job runs as whoever queued it, which may be any user of the site.
	settings.save(ignore_permissions=True)
