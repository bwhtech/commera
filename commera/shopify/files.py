import os
from urllib.parse import unquote, urlsplit

import frappe
import requests
from frappe import _

DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_IMAGE_BYTES = 20 * 1024 * 1024


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
	file_doc.file_name = os.path.basename(unquote(urlsplit(url).path)) or "shopify-image"
	file_doc.content = content
	file_doc.is_private = 0
	file_doc.attached_to_doctype = attached_to_doctype
	file_doc.attached_to_name = attached_to_name
	file_doc.insert(ignore_permissions=True)

	cache[key] = file_doc.file_url
	return file_doc.file_url
