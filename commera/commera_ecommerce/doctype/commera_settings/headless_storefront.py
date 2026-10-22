import frappe
from frappe import _
from frappe.utils import cstr, validate_url

OAUTH_APP_NAME = "Commera Storefront"
OAUTH_CALLBACK_PATH = "/account/authorize"
SHOPPER_ROLE = "Customer"


def sync_headless_oauth_client(settings) -> None:
	"""Point the storefront's OAuth client at its URL. An empty URL leaves the client as it is."""
	url = cstr(settings.headless_storefront_url).strip().rstrip("/")
	if not url:
		return
	if not validate_url(url, valid_schemes=("http", "https")):
		frappe.throw(_("Enter the storefront URL with http:// or https://."))

	settings.headless_storefront_url = url
	client = get_oauth_client(settings.headless_oauth_client)
	redirect_uri = f"{url}{OAUTH_CALLBACK_PATH}"
	client.update(
		{
			"app_name": OAUTH_APP_NAME,
			"redirect_uris": redirect_uri,
			"default_redirect_uri": redirect_uri,
			"scopes": "openid all",
			"grant_type": "Authorization Code",
			"response_type": "Code",
			"skip_authorization": 1,
			"token_endpoint_auth_method": "Client Secret Post",
		}
	)
	if SHOPPER_ROLE not in {row.role for row in client.allowed_roles}:
		client.append("allowed_roles", {"role": SHOPPER_ROLE})
	client.save(ignore_permissions=True)
	settings.headless_oauth_client = client.name


def get_oauth_client(name: str | None):
	if name and frappe.db.exists("OAuth Client", name):
		return frappe.get_doc("OAuth Client", name)
	return frappe.new_doc("OAuth Client")
