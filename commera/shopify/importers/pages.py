import frappe
from frappe import _
from frappe.utils import cint, cstr

from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import get_link, save_link
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, ResourceImporter, to_system_datetime
from commera.shopify.queries import PAGE_QUERIES
from commera.shopify.redirects import save_redirects

PAGE_DOCTYPE = "Shop Web Page"
PAGE_URL_PREFIX = "/en/page/"


class PageImporter(ResourceImporter):
	"""Shopify online store pages become Shop Web Pages. The page name is its title, which must be unique."""

	resource = "Pages"
	queries = PAGE_QUERIES

	def __init__(self, runner):
		super().__init__(runner)
		self.redirects = {}

	def import_record(self, page: dict) -> str:
		link = get_link(page["id"])
		if link and self.is_unchanged(link, page):
			return SKIPPED

		if link:
			page_doc = frappe.get_doc(PAGE_DOCTYPE, link.reference_name)
		else:
			page_doc = frappe.new_doc(PAGE_DOCTYPE)
			page_doc.name = get_free_page_name(page["title"])
			page_doc.route = get_free_route(page["handle"])

		# Content is mandatory on a Shop Web Page, and a Shopify page can be empty.
		page_doc.content = page.get("body") or page["title"]
		page_doc.published = cint(page.get("isPublished"))
		page_doc.save(ignore_permissions=True)

		self.redirects[f"pages/{page['handle']}"] = PAGE_URL_PREFIX + page_doc.route
		save_link(
			page["id"], self.resource, PAGE_DOCTYPE, page_doc.name, to_system_datetime(page.get("updatedAt"))
		)
		return UPDATED if link else CREATED

	def finish(self) -> None:
		save_redirects(self.redirects)


def get_free_page_name(title: str) -> str:
	title = cstr(title).strip() or _("Shopify page")
	candidate = title
	suffix = 2
	while frappe.db.exists(PAGE_DOCTYPE, candidate):
		candidate = f"{title} {suffix}"
		suffix += 1
	return candidate


def get_free_route(handle: str) -> str:
	candidate = handle
	suffix = 2
	while frappe.db.exists(PAGE_DOCTYPE, {"route": candidate}):
		candidate = f"{handle}-{suffix}"
		suffix += 1
	return candidate
