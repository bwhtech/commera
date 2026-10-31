import json
import os

import frappe
from frappe import _
from frappe.utils.data import cint, flt
from jinja2 import pass_context
from markupsafe import Markup, escape

import commera.sdk
from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context, is_within_directory
from commera.shop_themes.jinja_helpers import find_theme_asset_url
from commera.shop_themes.theme_resolver import find_theme_file

LAYOUT_CACHE_PREFIX = "commera:theme_layout:"
TEXT_TYPES = frozenset({"text", "textarea", "url", "image"})
DEFAULT_MAX_BLOCKS = 50
DEFAULT_MAX_PRODUCTS = 8
PASS_THROUGH_IMAGE_PREFIXES = ("http://", "https://", "/assets/")
SORT_BY_SOURCE = {"newest": "new_arrival", "on_sale": "discount", "collection": "default"}
SECTION_GROUPS = frozenset({"header_group", "footer_group"})
DEFAULT_SECTION_GROUPS = ("pages",)

theme_json_files = {}
image_urls = {}
classic_layout_calls = set()


def get_theme_json(theme_dirs, relative_path):
	path = find_theme_file(theme_dirs, relative_path)
	if not path:
		return None

	modified_time = os.path.getmtime(path)
	cached = theme_json_files.get(path)
	if cached and cached[0] == modified_time:
		return cached[1]

	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-security-file-traversal
	with open(path) as json_file:
		data = json.load(json_file)
	theme_json_files[path] = (modified_time, data)
	return data


def get_section_schema(theme_dirs, section_type):
	if not isinstance(section_type, str) or not section_type.replace("_", "").isalnum():
		return None
	return get_theme_json(theme_dirs, f"sections/{section_type}.json")


def get_page_layout(theme_name, theme_dirs, page):
	cache_key = f"{LAYOUT_CACHE_PREFIX}{theme_name}:{page}"
	cached = frappe.cache.get_value(cache_key)
	if cached is None:
		published_layout = frappe.db.get_value(
			"Theme Layout", {"theme": theme_name, "page": page}, "published_layout"
		)
		cached = {"layout": frappe.parse_json(published_layout) if published_layout else None}
		frappe.cache.set_value(cache_key, cached)

	return cached["layout"] or get_theme_json(theme_dirs, f"layouts/{page}.json") or {"sections": []}


def get_editor_preview():
	return getattr(frappe.local, "theme_editor_preview", None)


def clear_layout_cache(theme_name, page):
	frappe.cache.delete_value(f"{LAYOUT_CACHE_PREFIX}{theme_name}:{page}")


def get_text(value):
	if not isinstance(value, dict):
		return value
	return value.get(frappe.local.lang) or value.get("en") or next(iter(value.values()), "")


def get_image_url(theme_context, path):
	if not path or path.startswith(PASS_THROUGH_IMAGE_PREFIXES):
		return path or None

	cache_key = (frappe.local.site, theme_context["theme_name"], path)
	if cache_key not in image_urls:
		image_urls[cache_key] = find_image_url(theme_context, path)
	return image_urls[cache_key]


def find_image_url(theme_context, path):
	if path.startswith("/files/"):
		files_dir = frappe.get_site_path("public", "files")
		file_path = frappe.get_site_path("public", path.lstrip("/"))
		return path if is_within_directory(files_dir, file_path) and os.path.isfile(file_path) else None
	if path.startswith("/"):
		return path
	return find_theme_asset_url(theme_context, path)


def get_setting_value(setting, value, theme_context):
	setting_type = setting.get("type")
	if setting_type == "image":
		image_url = get_image_url(theme_context, get_text(value)) or get_image_url(
			theme_context, get_text(setting.get("default"))
		)
		return escape(image_url or "")
	if setting_type in TEXT_TYPES:
		return escape(get_text(value) or "")
	if setting_type == "number":
		return flt(value)
	if setting_type == "checkbox":
		return bool(cint(value))
	if setting_type == "products":
		return [str(code) for code in value or []]
	return value


def get_settings(schema_settings, saved_settings, theme_context):
	saved_settings = saved_settings if isinstance(saved_settings, dict) else {}
	return frappe._dict(
		{
			setting["id"]: get_setting_value(
				setting, saved_settings.get(setting["id"], setting.get("default")), theme_context
			)
			for setting in schema_settings or []
		}
	)


def get_section(schema, saved_section, theme_context, editor_mode=False):
	block_schemas = schema.get("blocks") or {}
	blocks = [
		frappe._dict(
			id=block.get("id"),
			type=block.get("type"),
			settings=get_settings(
				block_schemas[block.get("type")].get("settings"), block.get("settings"), theme_context
			),
			editor_attributes=get_editor_attributes("data-commera-block", block.get("id"), editor_mode),
		)
		for block in saved_section.get("blocks") or []
		if isinstance(block, dict) and block.get("type") in block_schemas
	]
	return frappe._dict(
		id=saved_section.get("id"),
		type=saved_section.get("type"),
		settings=get_settings(schema.get("settings"), saved_section.get("settings"), theme_context),
		blocks=blocks[: cint(schema.get("max_blocks")) or DEFAULT_MAX_BLOCKS],
	)


def get_editor_attributes(attribute, entry_id, editor_mode):
	if not editor_mode:
		return Markup("")
	return Markup(' {0}="{1}"').format(Markup(attribute), entry_id or "")


@pass_context
def render_layout(context, page):
	theme_context = get_render_theme_context()
	theme_dirs = theme_context["dirs"]
	if not theme_dirs:
		return ""
	if theme_context.get("theme_type") == "Classic":
		log_classic_layout_call(theme_context["theme_name"], page)
		return ""

	editor_preview = get_editor_preview()
	layout = editor_preview.layouts.get(page) if editor_preview else None
	if layout is None:
		layout = get_page_layout(theme_context["theme_name"], theme_dirs, page)
	section_context = {**context.get_all(), "commera": commera.sdk}
	editor_group = page if editor_preview else None
	html = [
		render_section(context.environment, theme_context, saved_section, section_context, editor_group)
		for saved_section in layout.get("sections") or []
		if isinstance(saved_section, dict) and not saved_section.get("hidden")
	]
	return Markup("\n".join(html))


def log_classic_layout_call(theme_name, page):
	call = (frappe.local.site, theme_name, page)
	if call in classic_layout_calls:
		return
	classic_layout_calls.add(call)
	frappe.log_error(
		title=_("render_layout called on a Classic theme"),
		message=_(
			'{0} is a Classic theme, so render_layout("{1}") renders nothing. '
			"Set its Theme Type to Sections, or hardcode the page."
		).format(theme_name, page),
	)


def render_section(environment, theme_context, saved_section, section_context, editor_group=None):
	schema = get_section_schema(theme_context["dirs"], saved_section.get("type"))
	if not schema:
		return ""

	editor_mode = bool(editor_group)
	try:
		section = get_section(schema, saved_section, theme_context, editor_mode)
		if section.settings.get("source"):
			section.products = get_section_products(
				section.settings, cint(schema.get("max_products")) or DEFAULT_MAX_PRODUCTS
			)
			if not section.products:
				return ""
		template = environment.get_template(f"theme://sections/{section.type}.html")
		html = template.render({**section_context, "section": section})
		if not editor_mode or not html.strip():
			return html
		return Markup("<div{0}{1}>{2}</div>").format(
			get_editor_attributes("data-commera-group", editor_group, editor_mode),
			get_editor_attributes("data-commera-section", section.id, editor_mode),
			Markup(html),
		)
	except Exception:
		frappe.log_error(title=_("Theme section {0} failed to render").format(saved_section.get("type")))
		return ""


def get_section_products(settings, limit):
	source = settings.source
	if source == "hand_picked":
		return (
			commera.sdk.catalog.get_product_cards_for(settings.products)[:limit] if settings.products else []
		)
	if source not in SORT_BY_SOURCE or (source == "collection" and not settings.collection):
		return []

	try:
		page = commera.sdk.catalog.list_products(
			collection=settings.collection if source == "collection" else None,
			on_sale=source == "on_sale",
			sort=SORT_BY_SOURCE[source],
			page_size=limit,
		)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return []
	return page["products"]


def validate_layout(theme_context, layout, page=None):
	if not isinstance(layout, dict) or not isinstance(layout.get("sections"), list):
		frappe.throw(_('A layout must be an object with a "sections" list.'))

	group = page if page in SECTION_GROUPS else "pages"

	references = frappe._dict(images=[], products=[], collections=[])
	section_ids = set()
	for section in layout["sections"]:
		validate_entry(section, section_ids, _("Section"))
		schema = get_section_schema(theme_context["dirs"], section["type"])
		if not schema:
			frappe.throw(_("Section type {0} does not exist in this theme.").format(section["type"]))
		if group not in (schema.get("groups") or DEFAULT_SECTION_GROUPS) or (
			page and schema.get("pages") and page not in schema["pages"]
		):
			frappe.throw(_("Section type {0} cannot be used in {1}.").format(section["type"], page or group))
		if not isinstance(section.get("hidden", False), bool):
			frappe.throw(_("Section {0}: hidden must be true or false.").format(section["id"]))
		validate_settings(schema.get("settings"), section.get("settings"), section["id"], references)
		validate_blocks(schema, section, references)

	validate_references(theme_context, references)
	if page:
		validate_required_sections(theme_context, layout, page)


def validate_required_sections(theme_context, layout, page):
	default_layout = get_theme_json(theme_context["dirs"], f"layouts/{page}.json") or {}
	shown = {section["type"] for section in layout["sections"] if not section.get("hidden")}
	for section in default_layout.get("sections") or []:
		schema = get_section_schema(theme_context["dirs"], section["type"]) or {}
		if schema.get("required") and section["type"] not in shown:
			frappe.throw(_("The {0} page needs its {1} section.").format(page, section["type"]))


def validate_blocks(schema, section, references):
	blocks = section.get("blocks") or []
	if not isinstance(blocks, list):
		frappe.throw(_("Section {0}: blocks must be a list.").format(section["id"]))

	max_blocks = cint(schema.get("max_blocks")) or DEFAULT_MAX_BLOCKS
	if len(blocks) > max_blocks:
		frappe.throw(_("Section {0} allows at most {1} blocks.").format(section["id"], max_blocks))

	block_schemas = schema.get("blocks") or {}
	block_ids = set()
	for block in blocks:
		validate_entry(block, block_ids, _("Block"))
		if block["type"] not in block_schemas:
			frappe.throw(
				_("Section {0} does not allow blocks of type {1}.").format(section["id"], block["type"])
			)
		validate_settings(
			block_schemas[block["type"]].get("settings"), block.get("settings"), block["id"], references
		)


def validate_entry(entry, seen_ids, label):
	if not isinstance(entry, dict) or not entry.get("id") or not entry.get("type"):
		frappe.throw(_("{0} entries need an id and a type.").format(label))
	if entry["id"] in seen_ids:
		frappe.throw(_("{0} id {1} is used twice.").format(label, entry["id"]))
	seen_ids.add(entry["id"])


def validate_settings(schema_settings, saved_settings, owner_id, references):
	saved_settings = saved_settings or {}
	if not isinstance(saved_settings, dict):
		frappe.throw(_("{0}: settings must be an object.").format(owner_id))

	settings_by_id = {setting["id"]: setting for setting in schema_settings or []}
	for setting_id, value in saved_settings.items():
		setting = settings_by_id.get(setting_id)
		if not setting:
			frappe.throw(_("{0}: unknown setting {1}.").format(owner_id, setting_id))
		if not is_valid_value(setting, value):
			frappe.throw(_("{0}: setting {1} has the wrong type.").format(owner_id, setting_id))

	add_references(settings_by_id, saved_settings, owner_id, references)


def add_references(settings_by_id, saved_settings, owner_id, references):
	source = saved_settings.get("source", (settings_by_id.get("source") or {}).get("default"))
	for setting_id, value in saved_settings.items():
		setting_type = settings_by_id[setting_id].get("type")
		if setting_type == "image" and value:
			references.images.extend((owner_id, image) for image in get_texts(value) if image)
		elif setting_type == "products" and value and source in (None, "hand_picked"):
			references.products.extend((owner_id, code) for code in value)
		elif setting_type == "collection" and value and source == "collection":
			references.collections.append((owner_id, value))


def get_texts(value):
	return list(value.values()) if isinstance(value, dict) else [value]


def validate_references(theme_context, references):
	validate_images(theme_context, references.images)
	validate_products(references.products)
	validate_collections(references.collections)


def validate_images(theme_context, images):
	file_urls = {image for _owner_id, image in images if image.startswith("/files/")}
	saved_file_urls = (
		set(frappe.get_all("File", filters={"file_url": ("in", list(file_urls))}, pluck="file_url"))
		if file_urls
		else set()
	)
	for owner_id, image in images:
		if image.startswith("/files/"):
			if image not in saved_file_urls:
				frappe.throw(_("{0}: image {1} is not an uploaded file.").format(owner_id, image))
		elif not image.startswith(("/", *PASS_THROUGH_IMAGE_PREFIXES)) and not find_theme_asset_url(
			theme_context, image
		):
			frappe.throw(_("{0}: image {1} does not exist in this theme.").format(owner_id, image))


def validate_products(products):
	if not products:
		return
	published = set(
		frappe.get_all(
			"Style Attribute Variant",
			filters={"name": ("in", list({code for _owner_id, code in products})), "is_published": 1},
			pluck="name",
		)
	)
	for owner_id, code in products:
		if code not in published:
			frappe.throw(_("{0}: product {1} does not exist or is not published.").format(owner_id, code))


def validate_collections(collections):
	if not collections:
		return
	handles = {collection["handle"] for collection in commera.sdk.catalog.list_collections()}
	for owner_id, handle in collections:
		if handle not in handles:
			frappe.throw(_("{0}: collection {1} does not exist.").format(owner_id, handle))


def is_valid_value(setting, value):
	setting_type = setting.get("type")
	if value is None:
		return True
	if setting_type == "select":
		return value in (setting.get("options") or [])
	if setting_type == "collection":
		return isinstance(value, str)
	if setting_type in TEXT_TYPES:
		if isinstance(value, dict):
			return all(isinstance(text, str) for text in value.values())
		return isinstance(value, str)
	if setting_type == "number":
		return isinstance(value, int | float) and not isinstance(value, bool)
	if setting_type == "checkbox":
		return isinstance(value, bool)
	if setting_type == "products":
		return isinstance(value, list) and all(isinstance(code, str) for code in value)
	return False
