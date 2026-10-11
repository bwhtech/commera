# Copyright (c) 2026, company@bwhstudios.com and contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import settings as admin_settings
from commera.migrate import (
	DEFAULT_EMAIL_TEMPLATES,
	assign_default_email_templates,
	create_default_email_templates,
)

SETTINGS_DOCTYPE = "Commera Settings"


def set_email_templates(values):
	for fieldname, template in values.items():
		frappe.db.set_single_value(SETTINGS_DOCTYPE, fieldname, template)
	frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)


def read_email_templates():
	return {
		fieldname: frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
		for fieldname in DEFAULT_EMAIL_TEMPLATES
	}


def create_custom_template(name):
	if not frappe.db.exists("Email Template", name):
		frappe.get_doc({"doctype": "Email Template", "name": name, "subject": name, "response": name}).insert(
			ignore_permissions=True
		)
	return name


class TestDefaultEmailTemplates(IntegrationTestCase):
	def setUp(self):
		create_default_email_templates()

	def test_empty_fields_get_the_default_templates(self):
		set_email_templates(dict.fromkeys(DEFAULT_EMAIL_TEMPLATES, ""))

		assign_default_email_templates()

		self.assertEqual(read_email_templates(), DEFAULT_EMAIL_TEMPLATES)

	def test_a_chosen_template_is_kept(self):
		custom = create_custom_template("Test Custom Order Confirmation")
		set_email_templates(
			{
				"order_confirmation_email_template": custom,
				"order_cancellation_email_template": "",
				"item_in_stock_email_template": "",
			}
		)

		assign_default_email_templates()

		templates = read_email_templates()
		self.assertEqual(templates["order_confirmation_email_template"], custom)
		self.assertEqual(templates["order_cancellation_email_template"], "Order Cancellation")
		self.assertEqual(templates["item_in_stock_email_template"], "Item In Stock")

	def test_store_settings_save_once_the_defaults_are_in(self):
		set_email_templates(dict.fromkeys(DEFAULT_EMAIL_TEMPLATES, ""))
		with self.assertRaises(frappe.MandatoryError):
			admin_settings.save_store_settings(store_name="Template Test Store")

		assign_default_email_templates()
		frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

		saved = admin_settings.save_store_settings(store_name="Template Test Store")
		self.assertEqual(saved["store_name"], "Template Test Store")


class TestSettingsTabEndpoints(IntegrationTestCase):
	def setUp(self):
		create_default_email_templates()
		assign_default_email_templates()

	def test_a_template_choice_is_saved_and_read_back(self):
		custom = create_custom_template("Test Custom Back In Stock")

		admin_settings.save_tab_settings("emails", item_in_stock_email_template=custom)
		frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

		self.assertEqual(admin_settings.get_tab_settings("emails")["item_in_stock_email_template"], custom)

	def test_fields_outside_the_tab_are_ignored(self):
		store_name = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_name")

		admin_settings.save_tab_settings("emails", store_name="Not From This Tab")

		self.assertEqual(frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_name"), store_name)

	def test_an_unknown_tab_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			admin_settings.save_tab_settings("company_secrets", store_name="Not A Tab")

	def test_email_templates_are_not_repeated_on_the_advanced_tab(self):
		advanced_fieldnames = {
			field["fieldname"]
			for group in admin_settings.get_advanced_settings()["groups"]
			for field in group["fields"]
		}

		self.assertFalse(advanced_fieldnames & set(DEFAULT_EMAIL_TEMPLATES))
