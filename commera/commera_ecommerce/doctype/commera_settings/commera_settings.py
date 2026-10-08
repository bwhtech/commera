# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from bwh_payments.bwh_payments.utils import get_available_payment_modes
from frappe.model.document import Document
from frappe.utils import get_url_to_form
from frappe.website.utils import clear_cache as clear_website_cache

from commera.search.build import enqueue_full_rebuild
from commera.search.record_builder import ALLOWED_CONTENT_DOCTYPES, is_indexable_content_field
from commera.search.result_card import (
	MANDATORY_RESULT_FIELDS,
	MAX_RESULT_FIELDS,
	MIN_RESULT_FIELDS,
	RESULT_CARD_CATALOG,
)
from commera.storefront_plugins import clear_storefront_plugin_cache, get_enabled_storefront_apps

MAX_CONTENT_FIELDS = 15


class CommeraSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commera.commera_ecommerce.doctype.commera_storefront_app.commera_storefront_app import (
			CommeraStorefrontApp,
		)
		from commera.commera_ecommerce.doctype.footer_section_mapping.footer_section_mapping import (
			FooterSectionMapping,
		)
		from commera.commera_ecommerce.doctype.item_group_map.item_group_map import ItemGroupMap
		from commera.commera_ecommerce.doctype.return_reason.return_reason import ReturnReason
		from commera.commera_ecommerce.doctype.search_content_field.search_content_field import (
			SearchContentField,
		)
		from commera.commera_ecommerce.doctype.search_result_field.search_result_field import (
			SearchResultField,
		)

		accent_color: DF.Color | None
		allow_guest_checkout: DF.Check
		attribute_name_field: DF.Data | None
		badge_bg_color: DF.Color | None
		based_on_attribute: DF.Link | None
		border_accent_color: DF.Color | None
		brand_logo: DF.AttachImage | None
		brand_text_color: DF.Color | None
		button_bg_color: DF.Color | None
		cc_email: DF.Data | None
		charge_account_head: DF.Link | None
		cod_charge: DF.Currency
		cod_charge_applicable_below: DF.Currency
		cod_enabled: DF.Check
		company: DF.Link
		contact_email: DF.Data | None
		contact_phone: DF.Data | None
		copyright_text: DF.Data | None
		create_variants_automatically_on_configurator_creation: DF.Check
		default_meta_description: DF.SmallText | None
		default_price_list: DF.Link | None
		default_share_image: DF.AttachImage | None
		ecommerce_item_group_mapping: DF.Table[ItemGroupMap]
		ecommerce_warehouse: DF.Link | None
		facebook_url: DF.Data | None
		favicon: DF.Attach | None
		focus_ring_color: DF.Color | None
		footer_bg_color: DF.Color | None
		footer_logo: DF.AttachImage | None
		footer_sections: DF.Table[FooterSectionMapping]
		footer_text_color: DF.Color | None
		form_accent_color: DF.Color | None
		heading_accent_color: DF.Color | None
		homepage_meta_description: DF.SmallText | None
		homepage_meta_title: DF.Data | None
		homepage_og_image: DF.AttachImage | None
		instagram_url: DF.Data | None
		item_in_stock_email_template: DF.Link
		link_color: DF.Color | None
		link_hover_color: DF.Color | None
		llms_txt: DF.Code | None
		logo_url: DF.Data | None
		newsletter_description: DF.Text | None
		newsletter_title: DF.Data | None
		order_cancellation_email_template: DF.Link
		order_confirmation_email_template: DF.Link
		payment_methods_image: DF.AttachImage | None
		primary_color: DF.Color | None
		primary_hover_color: DF.Color | None
		print_format: DF.Link | None
		product_list_meta_description: DF.SmallText | None
		product_list_meta_title: DF.Data | None
		product_list_og_image: DF.AttachImage | None
		products_per_page: DF.Literal["12", "24", "48"]
		reason_for_return: DF.Table[ReturnReason]
		return_period: DF.Int
		sale_price_list: DF.Link | None
		search_content_fields: DF.Table[SearchContentField]
		search_result_fields: DF.Table[SearchResultField]
		secondary_accent_color: DF.Color | None
		seo_title_template: DF.Data | None
		shipping_rule: DF.Link | None
		sitemap_urls_per_page: DF.Int
		snapchat_url: DF.Data | None
		store_name: DF.Data | None
		store_pickup_enabled: DF.Check
		storefront_apps: DF.Table[CommeraStorefrontApp]
		strikethrough_color: DF.Color | None
		tiktok_url: DF.Data | None
		twitter_handle: DF.Data | None
		twitter_url: DF.Data | None
		vat_certificate_image: DF.AttachImage | None
		working_hours: DF.Data | None
	# end: auto-generated types

	pass

	def validate(self):
		self.validate_a_payment_method_is_available()
		self.validate_search_content_fields()
		self.validate_search_result_fields()

	def validate_a_payment_method_is_available(self):
		if self.cod_enabled or get_available_payment_modes():
			return
		frappe.throw(
			frappe._("Enable cash on delivery or at least one Payment Gateway Profile before saving.")
		)

	def validate_search_content_fields(self):
		rows = self.search_content_fields or []
		if len(rows) > MAX_CONTENT_FIELDS:
			frappe.throw(
				frappe._("You can index at most {0} search content fields.").format(MAX_CONTENT_FIELDS)
			)
		pairs = [(row.search_doctype, row.field) for row in rows]
		if len(pairs) != len(set(pairs)):
			frappe.throw(frappe._("Duplicate search content fields are not allowed."))

	def validate_search_result_fields(self):
		"""Reject an invalid result-card config; an empty table falls back to the default layout."""
		rows = self.search_result_fields or []
		if not rows:
			return

		fields = [row.field for row in rows]

		unknown = [field for field in fields if field not in RESULT_CARD_CATALOG]
		if unknown:
			frappe.throw(frappe._("Unknown search result card field(s): {0}").format(", ".join(unknown)))

		if len(fields) != len(set(fields)):
			frappe.throw(frappe._("Each search result card field can be listed only once."))

		enabled = [row.field for row in rows if row.show]
		disabled_mandatory = [field for field in MANDATORY_RESULT_FIELDS if field not in enabled]
		if disabled_mandatory:
			labels = ", ".join(RESULT_CARD_CATALOG[field] for field in disabled_mandatory)
			frappe.throw(frappe._("These search result card fields must stay enabled: {0}").format(labels))

		if not MIN_RESULT_FIELDS <= len(enabled) <= MAX_RESULT_FIELDS:
			frappe.throw(
				frappe._("Enable between {0} and {1} search result card fields.").format(
					MIN_RESULT_FIELDS, MAX_RESULT_FIELDS
				)
			)

	@frappe.whitelist()
	def get_result_card_field_options(self):
		"""Newline-joined catalog keys for the Search Result Field grid Select."""
		return "\n".join(RESULT_CARD_CATALOG)

	@frappe.whitelist()
	def get_content_field_options(self, search_doctype: str):
		"""Newline-joined indexable field names of `search_doctype` for the Search Content Field Select."""
		if search_doctype not in ALLOWED_CONTENT_DOCTYPES:
			return ""
		fields = [
			field.fieldname
			for field in frappe.get_meta(search_doctype).fields
			if field.fieldname and is_indexable_content_field(search_doctype, field.fieldname)
		]
		return "\n".join(["", *fields])

	def on_update(self):
		before = self.get_doc_before_save()
		if get_enabled_storefront_apps(before) != get_enabled_storefront_apps(self):
			clear_storefront_plugin_cache()
			clear_website_cache()
		if frappe.flags.in_install or frappe.flags.in_migrate:
			return
		if before is None:
			return
		old_pairs = [(row.search_doctype, row.field) for row in (before.search_content_fields or [])]
		new_pairs = [(row.search_doctype, row.field) for row in (self.search_content_fields or [])]
		if old_pairs != new_pairs:
			enqueue_full_rebuild(deduplicate=True)

	def get_default_price_list(self):
		return self.default_price_list

	def get_sale_price_list(self):
		return self.sale_price_list

	@frappe.whitelist()
	def enqueue_publish_all_variants(self, attribute: str):
		log = create_configurator_log()
		frappe.enqueue(
			"commera.commera_ecommerce.doctype.commera_settings.commera_settings.generate_configurators_for_all_templates",
			queue="long",
			enqueue_after_commit=True,
			attribute=attribute,
			log_name=log.name,
		)
		link = get_url_to_form("Bulk Style Attribute Configurator Creation Log", log.name)

		return frappe._(f"Creating configurators. <a href='{link}'>View Log</a>")

	@frappe.whitelist()
	def sync_item_group_mapping_to_ecommerce_items(self):
		for mapping in self.ecommerce_item_group_mapping:
			frappe.db.set_value(
				"Style Attribute Variant",
				{"item_group": mapping.original_item_group},
				"item_group",
				mapping.ecommerce_item_group,
			)

	@frappe.whitelist()
	def install_demo_data(self):
		"""Seed the Summer demo storefront in the store's own currency.
		Not install_demo_data: its price lists are hardcoded USD, which blocks every Sales Invoice on a non-USD company.
		"""
		from commera.install_summer_demo import (
			CURRENCY_PROFILES,
			DEFAULT_CURRENCY,
			get_company_currency,
			install_summer_demo,
		)

		# A store already trading in a supported currency keeps it; anything else gets the default.
		currency = get_company_currency()
		if currency not in CURRENCY_PROFILES:
			currency = DEFAULT_CURRENCY

		frappe.enqueue(
			install_summer_demo,
			queue="long",
			timeout=3000,
			enqueue_after_commit=True,
			currency=currency,
		)

		return "Demo data installation has been queued. This may take a few minutes. Check the background jobs for progress."

	@frappe.whitelist()
	def publish_all_items(self):
		"""Publish all items to website"""
		from commera.publish_demo_items import publish_all_demo_items

		frappe.enqueue(
			publish_all_demo_items,
			queue="default",
			timeout=600,
			enqueue_after_commit=True,
		)

		return "Publishing all items to website. This may take a moment. Refresh the page after completion."

	def generate_theme_css(self):
		"""Generate CSS custom properties from color scheme settings"""
		return f"""
		<style>
		:root {{
			--ls-primary: {self.primary_color or "#b91c1c"};
			--ls-primary-hover: {self.primary_hover_color or "#991b1b"};
			--ls-link: {self.link_color or "#7f1d1d"};
			--ls-link-hover: {self.link_hover_color or "#991b1b"};
			--ls-accent: {self.accent_color or "#b91c1c"};
			--ls-border-accent: {self.border_accent_color or "#b91c1c"};
			--ls-button-bg: {self.button_bg_color or "#b91c1c"};
			--ls-strikethrough: {self.strikethrough_color or "#b91c1c"};
			--ls-badge-bg: {self.badge_bg_color or "#b91c1c"};
			--ls-heading-accent: {self.heading_accent_color or "#991b1b"};
			--ls-brand-text: {self.brand_text_color or "#b91c1c"};
			--ls-secondary-accent: {self.secondary_accent_color or "#991b1b"};
			--ls-form-accent: {self.form_accent_color or "#b91c1c"};
			--ls-focus-ring: {self.focus_ring_color or "#b91c1c"};
			--ls-carousel-dot: {self.accent_color or "#b91c1c"};
			--ls-footer-bg: {self.footer_bg_color or "#111827"};
			--ls-footer-text: {self.footer_text_color or "#ffffff"};
		}}

		/* Primary color utilities */
		.bg-primary {{ background-color: var(--ls-primary) !important; }}
		.text-primary {{ color: var(--ls-primary) !important; }}
		.border-primary {{ border-color: var(--ls-primary) !important; }}
		.hover\\:bg-primary-hover:hover {{ background-color: var(--ls-primary-hover) !important; }}
		.hover\\:text-primary-hover:hover {{ color: var(--ls-primary-hover) !important; }}
		.focus\\:border-primary:focus {{ border-color: var(--ls-primary) !important; }}

		/* Link color utilities */
		.text-link {{ color: var(--ls-link) !important; }}
		.hover\\:text-link-hover:hover {{ color: var(--ls-link-hover) !important; }}

		/* Accent color utilities */
		.bg-accent {{ background-color: var(--ls-accent) !important; }}
		.text-accent {{ color: var(--ls-accent) !important; }}
		.border-accent {{ border-color: var(--ls-border-accent) !important; }}
		.hover\\:bg-accent:hover {{ background-color: var(--ls-accent) !important; }}

		/* UI Element utilities */
		.bg-button {{ background-color: var(--ls-button-bg) !important; }}
		.text-strikethrough {{ color: var(--ls-strikethrough) !important; }}
		.bg-badge {{ background-color: var(--ls-badge-bg) !important; }}
		.text-heading-accent {{ color: var(--ls-heading-accent) !important; }}
		.text-brand {{ color: var(--ls-brand-text) !important; }}
		.text-secondary-accent {{ color: var(--ls-secondary-accent) !important; }}
		.bg-secondary-accent {{ background-color: var(--ls-secondary-accent) !important; }}
		.border-secondary-accent {{ border-color: var(--ls-secondary-accent) !important; }}
		.hover\\:bg-secondary-accent:hover {{ background-color: var(--ls-secondary-accent) !important; }}
		.accent-form {{ accent-color: var(--ls-form-accent) !important; }}
		.focus\\:ring-focus:focus {{ box-shadow: 0 0 0 2px var(--ls-focus-ring) !important; }}

		/* Footer utilities */
		.bg-footer {{ background-color: var(--ls-footer-bg) !important; }}
		.text-footer {{ color: var(--ls-footer-text) !important; }}
		</style>
		"""


def generate_configurators_for_all_templates(attribute: str, log_name: str):
	item = frappe.qb.DocType("Item")
	configurator = frappe.qb.DocType("Style Attribute Configurator")

	query = (
		frappe.qb.from_(item)
		.left_join(configurator)
		.on(item.name == configurator.item_template)
		.select(item.name)
		.where(configurator.item_template.isnull() & item.has_variants)
	)
	results = query.run(as_dict=True)
	configurator_log = frappe.get_doc("Bulk Style Attribute Configurator Creation Log", log_name)
	configurator_log.configurators = []

	for row in results:
		item_name = row.get("name")
		configurator = frappe.get_doc(
			{
				"doctype": "Style Attribute Configurator",
				"item_template": item_name,
				"item_attribute": attribute,
			}
		).insert(ignore_permissions=True)
		variants_generated = configurator.get_total_variants()
		# nosemgrep: frappe-manual-commit  # job checkpoint, a crash keeps the configurators already made
		frappe.db.commit()
		configurator_log.append(
			"configurators",
			{
				"style_attribute_configurator": configurator.name,
				"variants_created": variants_generated,
			},
		)
		configurator_log.save()


def create_configurator_log():
	return frappe.get_doc(
		{
			"doctype": "Bulk Style Attribute Configurator Creation Log",
		}
	).insert(ignore_permissions=True)
