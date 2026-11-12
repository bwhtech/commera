# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

import unittest
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image


def get_published_variant():
	rows = frappe.get_all("Style Attribute Variant", {"is_published": 1}, ["name"], limit=1)
	return rows[0] if rows else None


class TestOGImageTemplate(IntegrationTestCase):
	def make_template(self, **kwargs):
		# autoname is field:for_doctype (one row per DocType), and generate_preview commits past rollback.
		frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
		values = {
			"doctype": "OG Image Template",
			"for_doctype": "Style Attribute Variant",
			"enabled": 1,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.db.exists("OG Image Template", doc.name)
			and frappe.delete_doc("OG Image Template", doc.name, force=True)
		)
		return doc

	def test_before_insert_seeds_template_html_from_bundled_card(self):
		card_path = frappe.get_app_path("commera", "templates", "og", "product_card.html")
		with open(card_path) as card_file:
			bundled = card_file.read()

		doc = self.make_template()  # no template_html supplied
		self.assertEqual(doc.template_html, bundled)

	def test_before_insert_keeps_supplied_template_html(self):
		marker = f"<div>kept-{frappe.generate_hash(length=8)}</div>"
		doc = self.make_template(template_html=marker)
		self.assertEqual(doc.template_html, marker)

	def test_generate_preview_requires_system_manager(self):
		# frappe.only_for is a no-op while local.flags.in_test is set, so the gate needs the flag cleared.
		doc = self.make_template()
		original_user = frappe.session.user
		original_in_test = frappe.local.flags.in_test
		try:
			frappe.set_user("Guest")
			frappe.local.flags.in_test = False
			with self.assertRaises(frappe.PermissionError):
				doc.generate_preview()
		finally:
			frappe.local.flags.in_test = original_in_test
			frappe.set_user(original_user)

	def test_generate_preview_saves_single_file_and_sets_preview_image(self):
		if not get_published_variant():
			self.skipTest("No published Style Attribute Variant to preview against.")

		doc = self.make_template()
		fixed_jpeg = jpeg_bytes("red")

		with patch(
			"commera.og.generator.render_card_for_doc",
			return_value=fixed_jpeg,
		) as mocked:
			file_url = doc.generate_preview()

		mocked.assert_called_once()
		self.assertTrue(file_url.endswith(".jpg"))

		doc.reload()
		self.assertEqual(doc.preview_image, file_url)

		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "OG Image Template",
				"attached_to_name": doc.name,
				"file_url": file_url,
			},
		)
		self.assertEqual(len(files), 1)
		self.addCleanup(frappe.delete_doc, "File", files[0].name, force=True)

	def test_generate_preview_replaces_prior_file(self):
		if not get_published_variant():
			self.skipTest("No published Style Attribute Variant to preview against.")

		doc = self.make_template()
		with patch(
			"commera.og.generator.render_card_for_doc",
			return_value=jpeg_bytes("red"),
		):
			doc.generate_preview()
		with patch(
			"commera.og.generator.render_card_for_doc",
			return_value=jpeg_bytes("blue"),
		):
			doc.reload()
			second_url = doc.generate_preview()

		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "OG Image Template",
				"attached_to_name": doc.name,
			},
			pluck="name",
		)
		self.assertEqual(len(files), 1)
		for name in files:
			self.addCleanup(frappe.delete_doc, "File", name, force=True)
		doc.reload()
		self.assertEqual(doc.preview_image, second_url)


def jpeg_bytes(colour):
	buffer = BytesIO()
	Image.new("RGB", (10, 10), colour).save(buffer, format="JPEG")
	return buffer.getvalue()
