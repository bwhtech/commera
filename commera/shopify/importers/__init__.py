from commera.shopify.importers.collections import CollectionImporter
from commera.shopify.importers.customers import CustomerImporter
from commera.shopify.importers.pages import PageImporter
from commera.shopify.importers.products import ProductImporter
from commera.shopify.importers.redirects import RedirectImporter
from commera.shopify.importers.store import StoreImporter

# Import order matters: products read the collections, and every redirect needs its target to exist.
IMPORTERS = {
	importer.resource: importer
	for importer in (
		StoreImporter,
		CollectionImporter,
		ProductImporter,
		PageImporter,
		CustomerImporter,
		RedirectImporter,
	)
}
