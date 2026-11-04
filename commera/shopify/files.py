import os
import re
from html import unescape
from urllib.parse import unquote, urlsplit

import frappe
import requests
from frappe import _

DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_SOURCE_PATTERN = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.IGNORECASE)
SHOPIFY_FILE_PATHS = ("/cdn/shop/", "/s/files/")


def get_url_key(url: str) -> str:
	"""Shopify adds a version query to CDN URLs, so the same image can arrive with two URLs."""
	parts = urlsplit(url or "")
	return f"{parts.netloc}{parts.path}"


def download_image(url: str, attached_to_doctype: str, attached_to_name: str, cache: dict) -> str:
	"""Save a remote image as a public File and return its file_url. `cache` maps URL keys to file
	URLs for one run, so an image used by several pages downloads once."""
	key = get_url_key(url)
	if key in cache:
		return cache[key]

	file_name = os.path.basename(unquote(urlsplit(url).path)) or "shopify-image"
	# A re-run imports the same Shopify HTML again. The copy saved for this record last time is reused.
	existing = frappe.db.get_value(
		"File",
		{
			"attached_to_doctype": attached_to_doctype,
			"attached_to_name": attached_to_name,
			"file_name": file_name,
		},
		"file_url",
	)
	if existing:
		cache[key] = existing
		return existing

	response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, stream=True)
	response.raise_for_status()
	if not response.headers.get("Content-Type", "").startswith("image/"):
		frappe.throw(_("{0} is not an image.").format(url))

	content = b""
	for chunk in response.iter_content(chunk_size=1024 * 256):
		content += chunk
		if len(content) > MAX_IMAGE_BYTES:
			frappe.throw(_("{0} is larger than 20 MB.").format(url))

	file_doc = frappe.new_doc("File")
	file_doc.file_name = file_name
	file_doc.content = content
	file_doc.is_private = 0
	file_doc.attached_to_doctype = attached_to_doctype
	file_doc.attached_to_name = attached_to_name
	file_doc.insert(ignore_permissions=True)

	cache[key] = file_doc.file_url
	return file_doc.file_url


def get_shopify_image_url(src: str, shop_domain: str) -> str | None:
	"""The absolute URL of an image Shopify hosts, or None for an image hosted elsewhere."""
	src = unescape(src).strip()
	if src.startswith("//"):
		src = f"https:{src}"
	parts = urlsplit(src)
	host = parts.netloc.lower()
	if not host:
		return f"https://{shop_domain}{src}" if parts.path.startswith(SHOPIFY_FILE_PATHS) else None
	if (
		host == "cdn.shopify.com"
		or host.endswith(".myshopify.com")
		or parts.path.startswith(SHOPIFY_FILE_PATHS)
	):
		return src
	return None


def copy_html_images(
	html: str, attached_to_doctype: str, attached_to_name: str, cache: dict, shop_domain: str
) -> tuple[str, list[str]]:
	"""Download the Shopify-hosted images an HTML description shows and point it at the copies, so the
	description keeps working after the Shopify store closes. Returns the HTML and the URLs that failed."""
	failed = []

	def copy_image(match) -> str:
		url = get_shopify_image_url(match.group(3), shop_domain)
		if not url:
			return match.group(0)
		try:
			file_url = download_image(url, attached_to_doctype, attached_to_name, cache)
		except (requests.RequestException, frappe.ValidationError):
			failed.append(url)
			return match.group(0)
		return f"{match.group(1)}{match.group(2)}{file_url}{match.group(2)}"

	return IMAGE_SOURCE_PATTERN.sub(copy_image, html or ""), failed
