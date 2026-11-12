"""Card-only Chromium driver. No request is allowed to reach the network."""

import base64
import mimetypes
import os
import posixpath
import time
from urllib.parse import unquote, urlsplit

import frappe
from frappe.utils import get_files_path
from frappe.utils.chromium import CDPSocketClient, ChromiumManager, Page
from frappe.utils.pdf import get_host_url
from frappe.utils.preview import safe_execute

RENDER_DEADLINE = 180


def get_preview_from_html(html, format="jpg", width=1200, height=630, quality=85):
	generator, browser_id = ChromiumManager.acquire()
	session = page = None
	try:
		if not generator._devtools_url:
			generator._set_devtools_url()
		session = CardSession(generator._devtools_url)
		session.connect()
		context, error = session.send("Target.createBrowserContext", {"disposeOnDetach": True})
		if error:
			raise RuntimeError(error)
		page = Page(session, context["browserContextId"], "screenshot")
		page.set_media_emulation("screen")
		page.set_device_metrics(width, height)
		requests = CardRequests(page, html)
		requests.install()
		page.navigate(requests.url, wait_for=["load", "DOMContentLoaded", "networkIdle"])
		page.evaluate("document.fonts.ready", await_promise=True)
		return page.capture_screenshot(image_format="jpeg", quality=quality)
	finally:
		safe_execute(page and page.close)
		safe_execute(session and session.disconnect)
		generator.remove_browser(browser_id)
		proc = generator._chromium_process
		if proc is not None and proc.poll() is not None:
			generator._close_browser()


class CardSession(CDPSocketClient):
	def __init__(self, url):
		super().__init__(url)
		self.deadline = time.monotonic() + RENDER_DEADLINE

	async def _send(self, *args, **kwargs):
		remaining = self.deadline - time.monotonic()
		if remaining <= 0:
			raise TimeoutError("OG render deadline exceeded")
		self.COMMAND_TIMEOUT = min(120, remaining)
		return await super()._send(*args, **kwargs)


class CardRequests:
	def __init__(self, page, html):
		self.page = page
		self.html = html
		self.url = get_host_url().rstrip("/") + "/__commera_og_document__"
		self.initial = True

	def install(self):
		# No frame filter: child-frame requests must be blocked too.
		self.page.session.start_listener("Fetch.requestPaused", self.handle, self.page.session_id)
		self.page.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})

	def handle(self, future, response):
		params = response["params"]
		request = params["request"]
		body = content_type = None
		if (
			self.initial
			and request["url"] == self.url
			and params.get("resourceType") == "Document"
			and params.get("frameId") == self.page.frame_id
		):
			self.initial = False
			body, content_type = self.html.encode(), "text/html; charset=utf-8"
		elif params.get("resourceType") in {"Image", "Font", "Stylesheet"} and request.get("method") == "GET":
			path = public_resource_path(request["url"], self.url)
			if path:
				body = base64.b64decode(frappe.read_file(path, as_base64=True))
				content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
		if body is None:
			self.page.send(
				"Fetch.failRequest",
				{"requestId": params["requestId"], "errorReason": "BlockedByClient"},
				return_future=True,
			)
		else:
			self.page.send(
				"Fetch.fulfillRequest",
				{
					"requestId": params["requestId"],
					"responseCode": 200,
					"responseHeaders": [{"name": "Content-Type", "value": content_type}],
					"body": base64.b64encode(body).decode(),
				},
				return_future=True,
			)


def public_resource_path(url, document_url):
	parts = urlsplit(url)
	origin = urlsplit(document_url)
	path = unquote(parts.path)
	if (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc):
		return None
	if "\\" in path or "\x00" in path or posixpath.normpath(path) != path:
		return None
	if path.startswith("/files/"):
		root = os.path.realpath(get_files_path(is_private=False))
		target = os.path.realpath(os.path.join(root, path.removeprefix("/files/")))
	elif path.startswith("/assets/"):
		root = os.path.realpath(os.path.join(frappe.local.sites_path, "assets"))
		target = os.path.realpath(os.path.join(root, path.removeprefix("/assets/")))
		# App asset directories are symlinks into each app's public directory.
		app, _, relative = path.removeprefix("/assets/").partition("/")
		root = os.path.realpath(os.path.join(root, app))
		if not relative:
			return None
	else:
		return None
	if os.path.commonpath([root, target]) == root and os.path.isfile(target):
		return target
	return None
