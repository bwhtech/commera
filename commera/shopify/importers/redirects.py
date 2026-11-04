from commera.shopify.importers.base import UPDATED, ResourceImporter
from commera.shopify.queries import REDIRECT_QUERIES
from commera.shopify.redirects import save_redirects


class RedirectImporter(ResourceImporter):
	"""The store's own Shopify URL redirects. Redirects for imported products, collections and pages
	are written by their importers."""

	resource = "Redirects"
	queries = REDIRECT_QUERIES
	supports_changed_filter = False

	def __init__(self, runner):
		super().__init__(runner)
		self.redirects = {}

	def get_title(self, record: dict) -> str:
		return record.get("path")

	def import_record(self, redirect: dict) -> str:
		self.redirects[redirect["path"]] = redirect["target"]
		return UPDATED

	def finish(self) -> None:
		save_redirects(self.redirects)
