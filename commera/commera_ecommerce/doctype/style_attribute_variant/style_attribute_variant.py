# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cstr, flt
from frappe.website.utils import cleanup_page_name

from commera.api.variant_pricing import (
	get_base_price_rows_by_key,
	get_selling_price_lists,
	insert_item_prices,
)
from commera.plugin_events import add_changed_products


class StyleAttributeVariant(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from frappe.website.doctype.website_slideshow_item.website_slideshow_item import (
			WebsiteSlideshowItem,
		)

		from commera.commera_ecommerce.doctype.color_size_item.color_size_item import (
			ColorSizeItem,
		)

		attribute_name: DF.Data | None
		attribute_value: DF.Data
		average_rating: DF.Float
		configurator: DF.Link
		display_name: DF.Data
		images: DF.Table[WebsiteSlideshowItem]
		is_published: DF.Check
		item_group: DF.Link | None
		item_style: DF.Link
		json_ld: DF.Code | None
		meta_description: DF.SmallText | None
		meta_keywords: DF.Data | None
		meta_title: DF.Data | None
		noindex: DF.Check
		og_image: DF.AttachImage | None
		review_count: DF.Int
		route: DF.Data | None
		sizes: DF.Table[ColorSizeItem]

	# end: auto-generated types
	def validate(self):
		self.unpublish_if_incomplete_data()

	def before_save(self):
		if not self.route:
			self.route = self.scrub(self.name)
		self.update_item_group()

	def scrub(self, text):
		return cleanup_page_name(text).replace("_", "-")

	def update_item_group(self):
		if not self.item_group:
			self.item_group = frappe.db.get_value("Item", self.item_style, "item_group", cache=True)
			item_group_mapping = frappe.get_cached_doc("Commera Settings").ecommerce_item_group_mapping
			for mapping in item_group_mapping:
				if mapping.original_item_group == self.item_group:
					self.item_group = mapping.ecommerce_item_group
					break

	@frappe.whitelist(methods=["POST"])
	def add_images(self, file_urls: list[str] | str):
		self.check_permission("write")
		if isinstance(file_urls, str):
			file_urls = frappe.parse_json(file_urls)

		for file_url in file_urls:
			if not frappe.db.exists("File", {"file_url": file_url}):
				frappe.throw(_("Invalid file: {0}").format(file_url))
			self.append("images", {"image": file_url})

		self.save()

	@frappe.whitelist(methods=["POST"])
	def remove_image(self, file_url: str):
		self.check_permission("write")
		matching_rows = [row for row in self.images if row.image == file_url]
		if not matching_rows:
			frappe.throw(_("Image not found on this variant: {0}").format(file_url))

		for row in matching_rows:
			self.remove(row)

		self.save()

	@frappe.whitelist(methods=["POST"])
	def clear_images(self):
		self.check_permission("write")
		if not self.images:
			return
		self.set("images", [])
		self.save()

	@frappe.whitelist()
	def get_size_prices(self):
		frappe.has_permission("Item Price", ptype="read", throw=True)
		default_price_list, sale_price_list = get_selling_price_lists()
		item_codes = [row.item_code for row in self.sizes if row.item_code]
		price_row_by_key = get_base_price_rows_by_key(item_codes, [default_price_list, sale_price_list])

		def get_rate(item_code, price_list):
			price_row = price_row_by_key.get((cstr(item_code), price_list))
			return price_row.price_list_rate if price_row else None

		return {
			"default_price_list": default_price_list,
			"sale_price_list": sale_price_list,
			"sizes": [
				{
					"size": row.size,
					"item_code": row.item_code,
					"default_rate": get_rate(row.item_code, default_price_list),
					"sale_rate": get_rate(row.item_code, sale_price_list),
				}
				for row in self.sizes
				if row.item_code
			],
		}

	@frappe.whitelist(methods=["POST"])
	def save_size_prices(self, size_prices: list | str):
		frappe.has_permission("Item Price", ptype="write", throw=True)
		frappe.has_permission("Item Price", ptype="create", throw=True)
		size_prices = frappe.parse_json(size_prices)
		default_price_list, sale_price_list = get_selling_price_lists()

		valid_item_codes = {cstr(row.item_code) for row in self.sizes if row.item_code}
		rate_by_key = {}
		for entry in size_prices:
			item_code = cstr(entry.get("item_code"))
			if item_code not in valid_item_codes:
				frappe.throw(_("Item {0} is not a size of this variant").format(item_code))
			for price_list, rate in (
				(default_price_list, entry.get("default_rate")),
				(sale_price_list, entry.get("sale_rate")),
			):
				if flt(rate) > 0:
					rate_by_key[(item_code, price_list)] = flt(rate)

		if not rate_by_key:
			return {"created": 0, "updated": 0}

		existing_price_by_key = get_base_price_rows_by_key(
			list({key[0] for key in rate_by_key}), [default_price_list, sale_price_list]
		)

		updated_count = 0
		price_rows_to_insert = []
		for (item_code, price_list), rate in rate_by_key.items():
			existing_price = existing_price_by_key.get((item_code, price_list))
			if not existing_price:
				price_rows_to_insert.append(
					{"item_code": item_code, "price_list": price_list, "price_list_rate": rate}
				)
			elif flt(existing_price.price_list_rate) != rate:
				frappe.db.set_value("Item Price", existing_price.name, "price_list_rate", rate)
				updated_count += 1

		if updated_count:
			add_changed_products([self.item_style], "price")
		return {"created": insert_item_prices(price_rows_to_insert), "updated": updated_count}

	@frappe.whitelist(methods=["POST"])
	def receive_stock(self, received_quantities: dict | str, valuation_rates: dict | str | None = None):
		frappe.has_permission("Stock Entry", ptype="create", throw=True)

		received_quantities = frappe.parse_json(received_quantities)
		if not isinstance(received_quantities, dict):
			frappe.throw(_("received_quantities must map item codes to quantities"))

		valuation_rates = frappe.parse_json(valuation_rates) if valuation_rates else {}
		if not isinstance(valuation_rates, dict):
			frappe.throw(_("valuation_rates must map item codes to rates"))

		variant_item_codes = {cstr(row.item_code) for row in self.sizes if row.item_code}
		foreign_item_codes = sorted((set(received_quantities) | set(valuation_rates)) - variant_item_codes)
		if foreign_item_codes:
			frappe.throw(_("Item {0} is not a size of this variant").format(", ".join(foreign_item_codes)))

		receipt_quantities = {}
		for item_code, quantity in received_quantities.items():
			quantity = flt(quantity)
			if quantity < 0:
				frappe.throw(_("Receive Qty cannot be negative for {0}").format(item_code))
			if quantity:
				receipt_quantities[item_code] = quantity

		if not receipt_quantities:
			frappe.throw(_("Enter a Receive Qty for at least one size"))

		warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
		if not warehouse:
			frappe.throw(_("Set Ecommerce Warehouse in Commera Settings before receiving stock"))

		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.stock_entry_type = "Material Receipt"
		stock_entry.company = frappe.get_cached_value("Warehouse", warehouse, "company")
		for item_code, quantity in receipt_quantities.items():
			row = {"item_code": item_code, "qty": quantity, "t_warehouse": warehouse}
			valuation_rate = flt(valuation_rates.get(item_code))
			if valuation_rate < 0:
				frappe.throw(_("Valuation Rate cannot be negative for {0}").format(item_code))
			if valuation_rate:
				row["basic_rate"] = valuation_rate
				row["set_basic_rate_manually"] = 1
			stock_entry.append("items", row)
		stock_entry.insert()

		for row in stock_entry.items:
			if not row.basic_rate:
				row.allow_zero_valuation_rate = 1
		stock_entry.submit()
		return stock_entry.name

	def unpublish_if_incomplete_data(self):
		if not self.is_published:
			return
		if not self.images or not self.sizes:
			self.is_published = False
			if not self.images and not self.sizes:
				frappe.msgprint(frappe._("Cannot publish without Images and Sizes"))
			elif not self.images:
				frappe.msgprint(frappe._("Cannot publish without Images"))
			else:
				frappe.msgprint(frappe._("Cannot publish without Sizes"))
