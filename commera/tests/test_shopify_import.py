# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the Shopify import: bulk JSONL assembly, option planning, and each importer writing
# into Commera through a fake Shopify client.

from unittest.mock import patch
from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from commera.commera_ecommerce.doctype.shopify_import_run.shopify_import_run import start_run
from commera.commera_ecommerce.doctype.shopify_import_settings.shopify_import_settings import (
	normalize_shop_domain,
)
from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import get_linked_name
from commera.shopify.bulk import assemble_bulk_records
from commera.shopify.files import copy_html_images
from commera.shopify.mapping import plan_product
from commera.shopify.runner import ImportRunner
from commera.shopify.scan import get_product_findings


def make_product(
	suffix, title=None, options=None, variants=None, status="ACTIVE", images=1, updated="2026-10-01T10:00:00Z"
):
	"""A product in the shape assemble_bulk_records returns."""
	product_id = f"gid://shopify/Product/{suffix}"
	options = options if options is not None else [("Color", ["Red", "Blue"]), ("Size", ["S", "M"])]
	if variants is None:
		variants = []
		combinations = [[]]
		for _name, values in options:
			combinations = [[*combo, value] for combo in combinations for value in values]
		for position, combo in enumerate(combinations, start=1):
			variants.append(
				{
					"id": f"gid://shopify/ProductVariant/{suffix}{position}",
					"title": " / ".join(combo),
					"sku": f"SKU-{suffix}-{position}",
					"price": "40.00",
					"compareAtPrice": "50.00",
					"inventoryQuantity": 3,
					"inventoryPolicy": "DENY",
					"position": position,
					"selectedOptions": [
						{"name": name, "value": value}
						for (name, _values), value in zip(options, combo, strict=True)
					],
					"inventoryItem": {
						"tracked": True,
						"measurement": {"weight": {"unit": "GRAMS", "value": 250}},
					},
				}
			)
	return {
		"id": product_id,
		"handle": f"shopify-test-{suffix}".lower(),
		"title": title or f"Shopify Test {suffix}",
		"descriptionHtml": "<p>Soft cotton.</p>",
		"vendor": f"Vendor {suffix}",
		"status": status,
		"tags": [],
		"updatedAt": updated,
		"seo": {"title": "SEO title", "description": "SEO description"},
		"options": [
			{"name": name, "position": index, "optionValues": [{"name": value} for value in values]}
			for index, (name, values) in enumerate(options, start=1)
		],
		"children": {
			"ProductVariant": variants,
			"MediaImage": [
				{
					"id": f"gid://shopify/MediaImage/{suffix}{n}",
					"image": {"url": f"https://cdn.shopify.test/{suffix}-{n}.jpg"},
				}
				for n in range(images)
			],
		},
	}


class FakeShopifyClient:
	"""Answers bulk queries from in-memory records, by the connection the query asks for."""

	def __init__(self, records=None, shop=None):
		self.records = records or {}
		self.shop = shop or {
			"name": "Test Shop",
			"currencyCode": "INR",
			"primaryDomain": {"host": "shop.test"},
		}

	def execute(self, query, variables=None):
		if "shop {" in query:
			return {"shop": self.shop}
		return {"count": {"count": 0}}

	def iter_bulk_records(self, query):
		for connection in ("products", "collections", "customers", "pages", "urlRedirects"):
			if f"{connection}" in query.split("{", 2)[1]:
				return iter(self.records.get(connection, []))
		return iter([])


def fake_download_image(url, attached_to_doctype, attached_to_name, cache):
	if url in cache:
		return cache[url]
	file_doc = frappe.new_doc("File")
	# Not .jpg: Frappe would try to strip EXIF data from content that is not an image.
	file_doc.file_name = f"shopify-{frappe.generate_hash(length=8)}.txt"
	file_doc.content = frappe.generate_hash(length=32)
	file_doc.is_private = 0
	file_doc.insert(ignore_permissions=True)
	cache[url] = file_doc.file_url
	return file_doc.file_url


class TestBulkAssembly(UnitTestCase):
	def test_children_land_under_their_parent_by_type(self):
		lines = [
			{"id": "gid://shopify/Product/1"},
			{"id": "gid://shopify/Product/2"},
			{"id": "gid://shopify/ProductVariant/11", "__parentId": "gid://shopify/Product/1"},
			{"id": "gid://shopify/MediaImage/21", "__parentId": "gid://shopify/Product/2"},
		]
		records = list(assemble_bulk_records(lines))
		self.assertEqual(
			[record["id"] for record in records], ["gid://shopify/Product/1", "gid://shopify/Product/2"]
		)
		self.assertEqual(records[0]["children"]["ProductVariant"][0]["id"], "gid://shopify/ProductVariant/11")
		self.assertEqual(records[1]["children"]["MediaImage"][0]["id"], "gid://shopify/MediaImage/21")

	def test_a_child_before_its_parent_is_refused(self):
		with self.assertRaises(ValueError):
			list(
				assemble_bulk_records(
					[{"id": "gid://shopify/ProductVariant/1", "__parentId": "gid://shopify/Product/9"}]
				)
			)


class TestProductPlan(UnitTestCase):
	def test_colour_makes_pages_and_size_goes_to_the_picker(self):
		plan = plan_product(make_product("P1"), ["color", "colour"])
		self.assertEqual(plan.page_option, "Color")
		self.assertEqual(list(plan.pages), ["Red", "Blue"])
		self.assertEqual([row.size for row in plan.pages["Red"]], ["S", "M"])

	def test_a_third_option_is_joined_into_the_size_label(self):
		product = make_product("P2", options=[("Size", ["S"]), ("Colour", ["Red"]), ("Material", ["Cotton"])])
		plan = plan_product(product, ["color", "colour"])
		self.assertEqual(plan.page_option, "Colour")
		self.assertTrue(plan.joined_size_options)
		self.assertEqual(plan.pages["Red"][0].size, "S / Cotton")

	def test_without_a_colour_the_product_gets_one_page(self):
		plan = plan_product(make_product("P3", options=[("Material", ["Cotton", "Silk"])]), ["color"])
		self.assertFalse(plan.has_page_option)
		self.assertEqual(
			plan.get_option_sizes("Standard"), [{"option": "Standard", "sizes": ["Cotton", "Silk"]}]
		)

	def test_shopifys_default_title_option_is_no_option(self):
		product = make_product("P4", options=[("Title", ["Default Title"])])
		plan = plan_product(product, ["color"])
		self.assertEqual(plan.size_options, [])
		self.assertEqual(plan.get_option_sizes("Standard"), [{"option": "Standard", "sizes": []}])

	def test_scan_reports_joined_options_and_missing_images(self):
		products = [
			make_product("P5", options=[("Size", ["S"]), ("Color", ["Red"]), ("Fit", ["Slim"])]),
			make_product("P6", images=0),
		]
		titles = {
			finding["title"]: finding["examples"] for finding in get_product_findings(products, ["color"])
		}
		self.assertEqual(titles["More than two options"], ["Shopify Test P5"])
		self.assertEqual(titles["No images"], ["Shopify Test P6"])


class TestCustomerAddresses(UnitTestCase):
	def test_addresses_come_from_the_connection_or_the_older_inline_list(self):
		from commera.shopify.importers.customers import get_addresses

		child = {"id": "gid://shopify/MailingAddress/1", "address1": "A"}
		self.assertEqual(get_addresses({"children": {"MailingAddress": [child]}}), [child])
		self.assertEqual(get_addresses({"addresses": [child]}), [child])


class TestDescriptionImages(UnitTestCase):
	def test_shopify_images_are_copied_and_other_images_are_kept(self):
		html = (
			'<p><img src="https://cdn.shopify.com/s/files/1/a.jpg?v=1" alt="A">'
			"<img src='/cdn/shop/files/b.png'>"
			'<img src="https://images.example.com/c.jpg"></p>'
		)
		downloaded = []

		def fake_download(url, doctype, name, cache):
			downloaded.append(url)
			return f"/files/{url.rsplit('/', 1)[-1].split('?')[0]}"

		with patch("commera.shopify.files.download_image", side_effect=fake_download):
			result, failed = copy_html_images(html, "Item", "X", {}, "shop.myshopify.com")

		self.assertEqual(
			downloaded,
			[
				"https://cdn.shopify.com/s/files/1/a.jpg?v=1",
				"https://shop.myshopify.com/cdn/shop/files/b.png",
			],
		)
		self.assertEqual(
			result,
			'<p><img src="/files/a.jpg" alt="A">'
			"<img src='/files/b.png'>"
			'<img src="https://images.example.com/c.jpg"></p>',
		)
		self.assertEqual(failed, [])

	def test_an_image_that_fails_to_download_keeps_its_shopify_url(self):
		html = '<img src="https://cdn.shopify.com/s/files/1/gone.jpg">'
		with patch(
			"commera.shopify.files.download_image", side_effect=frappe.ValidationError("not an image")
		):
			result, failed = copy_html_images(html, "Item", "X", {}, "shop.myshopify.com")
		self.assertEqual(result, html)
		self.assertEqual(failed, ["https://cdn.shopify.com/s/files/1/gone.jpg"])


class TestShopDomain(UnitTestCase):
	def test_a_pasted_url_or_handle_becomes_the_myshopify_domain(self):
		self.assertEqual(
			normalize_shop_domain("https://My-Store.myshopify.com/admin"), "my-store.myshopify.com"
		)
		self.assertEqual(normalize_shop_domain("my-store"), "my-store.myshopify.com")

	def test_another_host_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			normalize_shop_domain("shop.example.com")


class ShopifyImportTestCase(IntegrationTestCase):
	def setUp(self):
		self.suffix = frappe.generate_hash(length=6).upper()
		settings = frappe.get_single("Shopify Import Settings")
		settings.update(
			{
				"shop_domain": "commera-test.myshopify.com",
				"auth_method": "Access Token",
				"access_token": "shpat_test",
				"page_option_names": "Color\nColour",
				"option_attribute": "Color",
				"default_collection": None,
				"publish_active_products": 1,
				"import_inventory": 1,
				"add_collections_to_menu": 0,
			}
		)
		settings.save()
		# The runner commits after every record. Here the test's own rollback must undo it all.
		self.commit_patch = patch.object(frappe.db, "commit")
		self.commit_patch.start()
		self.download_patch = patch(
			"commera.shopify.importers.product_pages.download_image", side_effect=fake_download_image
		)
		self.download_patch.start()

	def tearDown(self):
		self.commit_patch.stop()
		self.download_patch.stop()

	def run_import(self, records, resources, shop=None):
		run = start_run("Import", resources)
		with patch("commera.shopify.runner.ShopifyClient", return_value=FakeShopifyClient(records, shop)):
			ImportRunner(frappe.get_doc("Shopify Import Run", run.name)).execute()
		return frappe.get_doc("Shopify Import Run", run.name)

	def get_counts(self, run, resource):
		row = run.get_progress_row(resource)
		return {
			"created": row.created_count,
			"updated": row.updated_count,
			"skipped": row.skipped_count,
			"failed": row.failed_count,
		}


class TestProductImport(ShopifyImportTestCase):
	def test_a_product_becomes_colour_pages_with_sizes_prices_and_stock(self):
		product = make_product(self.suffix)
		run = self.run_import({"products": [product]}, ["Products"])

		self.assertEqual(run.status, "Completed", run.issues and run.issues[0].message)
		item_template = get_linked_name(product["id"])
		self.assertEqual(frappe.db.get_value("Item", item_template, "item_name"), product["title"])
		self.assertEqual(frappe.db.get_value("Item", item_template, "brand"), product["vendor"])

		pages = frappe.get_all(
			"Style Attribute Variant",
			filters={"item_style": item_template},
			fields=["name", "attribute_value", "route", "is_published", "meta_title"],
			order_by="attribute_value",
		)
		self.assertEqual([page.attribute_value for page in pages], ["Blue", "Red"])
		self.assertEqual({page.route for page in pages}, {product["handle"], f"{product['handle']}-blue"})
		self.assertTrue(all(page.is_published and page.meta_title == "SEO title" for page in pages))

		size_item = get_linked_name(product["children"]["ProductVariant"][0]["id"])
		self.assertEqual(frappe.db.get_value("Item", size_item, "weight_per_unit"), 250)
		self.assertEqual(frappe.db.get_value("Item", size_item, "custom_sku"), f"SKU-{self.suffix}-1")
		self.assertFalse(frappe.db.get_value("Item", item_template, "custom_sku"))
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.assertEqual(
			frappe.db.get_value(
				"Item Price", {"item_code": size_item, "price_list": sale_price_list}, "price_list_rate"
			),
			40,
		)
		warehouse = frappe.db.get_single_value("Commera Settings", "ecommerce_warehouse")
		self.assertEqual(
			frappe.db.get_value("Bin", {"item_code": size_item, "warehouse": warehouse}, "actual_qty"), 3
		)

	def test_description_images_are_copied_or_reported_when_erpnext_removes_them(self):
		product = make_product(self.suffix)
		product["descriptionHtml"] = '<p>Soft.</p><img src="https://cdn.shopify.com/s/files/1/soft.jpg">'
		frappe.db.set_single_value("Stock Settings", "clean_description_html", 0)
		with patch("commera.shopify.files.download_image", return_value="/files/soft.jpg"):
			run = self.run_import({"products": [product]}, ["Products"])

		self.assertEqual(
			frappe.db.get_value("Item", get_linked_name(product["id"]), "description"),
			'<p>Soft.</p><img src="/files/soft.jpg">',
		)
		self.assertFalse([issue for issue in run.issues if "Clean Description HTML" in issue.message])

		product["updatedAt"] = "2026-10-02T10:00:00Z"
		frappe.db.set_single_value("Stock Settings", "clean_description_html", 1)
		with patch("commera.shopify.files.download_image", return_value="/files/soft.jpg"):
			run = self.run_import({"products": [product]}, ["Products"])
		self.assertTrue([issue for issue in run.issues if "Clean Description HTML" in issue.message])

	def test_a_second_run_skips_an_unchanged_product_and_updates_a_changed_one(self):
		product = make_product(self.suffix)
		self.run_import({"products": [product]}, ["Products"])

		run = self.run_import({"products": [product]}, ["Products"])
		self.assertEqual(self.get_counts(run, "Products")["skipped"], 1)

		changed = make_product(self.suffix, updated="2026-10-02T10:00:00Z")
		for variant in changed["children"]["ProductVariant"]:
			variant["price"] = "35.00"
			variant["inventoryQuantity"] = 1
			variant["sku"] = f"NEW-{variant['sku']}"
		run = self.run_import({"products": [changed]}, ["Products"])
		self.assertEqual(self.get_counts(run, "Products")["updated"], 1)

		size_item = get_linked_name(changed["children"]["ProductVariant"][0]["id"])
		self.assertEqual(frappe.db.get_value("Item", size_item, "custom_sku"), f"NEW-SKU-{self.suffix}-1")
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.assertEqual(
			frappe.db.get_value(
				"Item Price", {"item_code": size_item, "price_list": sale_price_list}, "price_list_rate"
			),
			35,
		)
		warehouse = frappe.db.get_single_value("Commera Settings", "ecommerce_warehouse")
		self.assertEqual(
			frappe.db.get_value("Bin", {"item_code": size_item, "warehouse": warehouse}, "actual_qty"), 1
		)

	def test_a_repeated_title_gets_its_handle_in_the_product_code(self):
		first = make_product(f"{self.suffix}A", title=f"Same Tee {self.suffix}")
		second = make_product(f"{self.suffix}B", title=f"Same Tee {self.suffix}")
		run = self.run_import({"products": [first, second]}, ["Products"])

		self.assertEqual(self.get_counts(run, "Products")["created"], 2)
		self.assertEqual(get_linked_name(second["id"]), f"Same Tee {self.suffix} ({second['handle']})")
		self.assertEqual(
			frappe.db.get_value("Item", get_linked_name(second["id"]), "item_name"), f"Same Tee {self.suffix}"
		)

	def test_one_broken_product_does_not_stop_the_others(self):
		broken = make_product(f"{self.suffix}X", variants=[])
		good = make_product(f"{self.suffix}Y")
		run = self.run_import({"products": [broken, good]}, ["Products"])

		self.assertEqual(run.status, "Completed With Errors")
		self.assertEqual(
			self.get_counts(run, "Products"), {"created": 1, "updated": 0, "skipped": 0, "failed": 1}
		)
		self.assertIsNone(get_linked_name(broken["id"]))
		self.assertTrue(get_linked_name(good["id"]))

	def test_a_product_without_options_and_without_images_stays_unpublished(self):
		product = make_product(self.suffix, options=[("Title", ["Default Title"])], images=0)
		run = self.run_import({"products": [product]}, ["Products"])

		pages = frappe.get_all(
			"Style Attribute Variant", {"item_style": get_linked_name(product["id"])}, ["is_published"]
		)
		self.assertEqual(len(pages), 1)
		self.assertFalse(pages[0].is_published)
		self.assertTrue(any("left unpublished" in issue.message for issue in run.issues))


class TestCollectionCustomerPageImport(ShopifyImportTestCase):
	def test_a_product_lands_in_its_first_collection_and_the_old_url_redirects(self):
		product = make_product(self.suffix)
		collection = {
			"id": f"gid://shopify/Collection/{self.suffix}",
			"handle": f"summer-{self.suffix}".lower(),
			"title": f"Summer {self.suffix}",
			"descriptionHtml": "<p>Light layers.</p>",
			"seo": {"title": "Summer edit", "description": "Light layers for warm days."},
			"updatedAt": "2026-10-01T10:00:00Z",
			"children": {"Product": [{"id": product["id"]}]},
		}
		run = self.run_import(
			{"collections": [collection], "products": [product]}, ["Collections", "Products"]
		)

		self.assertEqual(run.status, "Completed", run.issues and run.issues[0].message)
		item_group = get_linked_name(collection["id"])
		self.assertEqual(
			frappe.db.get_value("Item", get_linked_name(product["id"]), "item_group"), item_group
		)
		self.assertEqual(
			frappe.db.get_value(
				"Item Group",
				item_group,
				["custom_description", "custom_meta_title", "custom_meta_description"],
			),
			("<p>Light layers.</p>", "Summer edit", "Light layers for warm days."),
		)
		# Shopify keeps updatedAt when only the text changes.
		collection["seo"] = {"title": "Summer sale", "description": ""}
		run = self.run_import({"collections": [collection]}, ["Collections"])
		self.assertEqual(self.get_counts(run, "Collections")["updated"], 1)
		self.assertEqual(frappe.db.get_value("Item Group", item_group, "custom_meta_title"), "Summer sale")
		run = self.run_import({"collections": [collection]}, ["Collections"])
		self.assertEqual(self.get_counts(run, "Collections")["skipped"], 1)

		targets = {row.source: row.target for row in frappe.get_single("Website Settings").route_redirects}
		self.assertEqual(
			targets[f"collections/summer\\-{self.suffix.lower()}"],
			f"/en/products?subcategory={quote(item_group)}",
		)

	def test_a_customer_gets_a_contact_and_an_address_and_is_not_duplicated(self):
		email = f"shopper-{self.suffix.lower()}@example.com"
		customer = {
			"id": f"gid://shopify/Customer/{self.suffix}",
			"displayName": "Asha Rao",
			"firstName": "Asha",
			"lastName": "Rao",
			"updatedAt": "2026-10-01T10:00:00Z",
			"defaultEmailAddress": {"emailAddress": email},
			"defaultAddress": {"id": f"gid://shopify/MailingAddress/{self.suffix}"},
			# addressesV2 is a connection, so the bulk file returns it as child lines.
			"children": {
				"MailingAddress": [
					{
						"id": f"gid://shopify/MailingAddress/{self.suffix}",
						"address1": "12 MG Road",
						"city": "Bengaluru",
						"zip": "560001",
						"countryCodeV2": "IN",
					}
				]
			},
		}
		self.run_import({"customers": [customer]}, ["Customers"])
		customer_name = get_linked_name(customer["id"])
		self.assertEqual(frappe.db.get_value("Customer", customer_name, "customer_name"), "Asha Rao")
		addresses = frappe.get_all(
			"Address",
			filters=[["Dynamic Link", "link_name", "=", customer_name]],
			fields=["city", "is_primary_address"],
		)
		self.assertEqual([(row.city, row.is_primary_address) for row in addresses], [("Bengaluru", 1)])

		customer["updatedAt"] = "2026-10-03T10:00:00Z"
		run = self.run_import({"customers": [customer]}, ["Customers"])
		self.assertEqual(self.get_counts(run, "Customers")["updated"], 1)
		self.assertEqual(
			len(frappe.get_all("Address", filters=[["Dynamic Link", "link_name", "=", customer_name]])), 1
		)

	def test_a_page_keeps_its_handle_as_route(self):
		page = {
			"id": f"gid://shopify/Page/{self.suffix}",
			"handle": f"about-{self.suffix}".lower(),
			"title": f"About {self.suffix}",
			"body": "<p>Hello</p>",
			"isPublished": True,
			"updatedAt": "2026-10-01T10:00:00Z",
		}
		self.run_import({"pages": [page]}, ["Pages"])
		self.assertEqual(
			frappe.db.get_value("Shop Web Page", get_linked_name(page["id"]), "route"), page["handle"]
		)


class TestStoreImport(ShopifyImportTestCase):
	def test_store_details_fill_empty_fields_without_a_payment_method(self):
		frappe.db.set_single_value("Commera Settings", {"store_name": None, "cod_enabled": 0})
		shop = {"name": f"Shop {self.suffix}", "currencyCode": "INR", "primaryDomain": {"host": "shop.test"}}
		with patch(
			"commera.commera_ecommerce.doctype.commera_settings.commera_settings.get_available_payment_modes",
			return_value=[],
		):
			run = self.run_import({}, ["Store"], shop)

		self.assertEqual(self.get_counts(run, "Store")["failed"], 0)
		self.assertEqual(frappe.db.get_single_value("Commera Settings", "store_name"), shop["name"])


class TestCollectionListing(IntegrationTestCase):
	def test_a_listing_of_one_collection_carries_its_text(self):
		from commera.api.admin.catalog import create_collection
		from commera.www.products.list import get_collection_header

		item_group = create_collection(f"Listing {frappe.generate_hash(length=6)}")["name"]
		frappe.db.set_value(
			"Item Group",
			item_group,
			{"custom_description": "<p>Warm wool.</p>", "custom_meta_title": "Wool edit"},
		)

		collection = get_collection_header([item_group])
		self.assertEqual(collection.description, "<p>Warm wool.</p>")
		self.assertEqual(collection.meta_title, "Wool edit")
		self.assertIsNone(get_collection_header([item_group, "Another"]))

	def test_a_shopify_product_link_inside_a_collection_opens_the_product(self):
		from frappe.website.path_resolver import resolve_redirect

		path = "collections/summer/products/linen-shirt"
		frappe.cache.hdel("website_redirects", path)
		with self.assertRaises(frappe.Redirect):
			resolve_redirect(path)
		self.assertEqual(frappe.flags.redirect_location, "/en/products/linen-shirt")
