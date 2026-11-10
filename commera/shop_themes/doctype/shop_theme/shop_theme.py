import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from string import Template

import frappe
from frappe.model.document import Document
from frappe.modules.utils import export_module_json

# frappe.scrub() does not strip path separators, so it is not a sanitiser.
THEME_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")

DEFAULT_THEME_APP = "commera"
DEFAULT_THEME_MODULE = "Shop Themes"
BASE_THEME = "Shop Base Theme"
THEME_FOLDERS = {
	"Classic": ("pages", "components/includes", "components/macros", "styles"),
	"Sections": ("pages", "sections", "layouts"),
}
SECTIONS_ONLY_FOLDERS = ("sections", "layouts")
THEME_STARTER_DIR = Path(__file__).parents[3] / "scaffold" / "starter" / "theme"
STARTER_TEXT_SUFFIXES = (".css", ".html", ".js", ".json", ".md", ".py", ".txt")

THEME_CONTEXT_CACHE_KEY = "shop_theme_context"
STYLE_TAB = "style_tab"
PREVIEW_THEME_PARAM = "preview_theme"


class ShopTheme(Document):
	def validate(self):
		validate_theme_name(self.theme_name)
		self.validate_unique_slug()
		if self.is_new():
			self.validate_theme_folder_can_exist()
			if self.can_scaffold() and not os.path.isdir(self.get_folder()):
				self.is_standard = 1
		if self.use_as_starter:
			self.validate_starter()
		if self.theme_type == "Classic":
			self.validate_classic_folders()
		if self.parent_theme:
			self.validate_no_circular_inheritance()
			self.validate_parent_theme_type()

	def validate_unique_slug(self):
		# "Foo Bar" and "Foo-Bar" scrub to the same slug, and on_trash rmtrees by slug: one delete takes both.
		# ponytail: scrubs every theme name in python, revisit if a site ever ships enough
		# themes for this to matter
		slug = frappe.scrub(self.theme_name)
		# "" rather than self.name: a new doc has no name yet, and `!= NULL` matches no rows.
		filters = {"name": ("!=", self.name or "")}
		for theme_name in frappe.get_all("Shop Theme", filters=filters, pluck="theme_name"):
			if frappe.scrub(theme_name) == slug:
				frappe.throw(frappe._("Theme {0} already uses the folder name {1}").format(theme_name, slug))

	def get_folder(self):
		app_path = frappe.get_app_path(get_app_for_module(self.module))
		return get_contained_path(os.path.join(app_path, "themes"), frappe.scrub(self.theme_name))

	def can_scaffold(self):
		return frappe.conf.developer_mode or self.flags.scaffold

	def validate_theme_folder_can_exist(self):
		if not self.can_scaffold() and not os.path.isdir(self.get_folder()):
			frappe.throw(
				frappe._(
					"Theme {0} has no folder yet. "
					"Create the theme with bench commera theme new, or turn on developer mode."
				).format(self.theme_name)
			)

	def validate_starter(self):
		if not self.is_standard or not os.path.isdir(self.get_folder()):
			frappe.throw(frappe._("Only a standard theme with a theme folder can be used as a starter"))

		starter = frappe.db.get_value(
			"Shop Theme",
			{"use_as_starter": 1, "theme_type": self.theme_type, "name": ("!=", self.name or "")},
		)
		if starter:
			frappe.throw(
				frappe._("{0} is already the {1} starter. Untick Use as Starter there first.").format(
					starter, self.theme_type
				)
			)

	def validate_classic_folders(self):
		theme_dir = self.get_folder()
		for folder in SECTIONS_ONLY_FOLDERS:
			if os.path.isdir(os.path.join(theme_dir, folder)):
				frappe.throw(
					frappe._(
						"{0} is a Classic theme, but its folder has {1}/. Only Sections themes use {1}/: "
						"remove the folder or set Theme Type to Sections."
					).format(self.theme_name, folder)
				)

	def after_insert(self):
		# A read-only apps volume would otherwise break the insert itself.
		if not self.can_scaffold():
			return

		starter = None if os.path.isdir(self.get_folder()) else self.get_starter()
		self.flags.scaffold_changes = scaffold_theme(
			self.theme_name, self.module, self.theme_type, parent_theme=self.parent_theme
		)
		if starter and starter.theme_settings:
			settings_doctype = f"{self.theme_name} Settings"
			copy_starter_settings_doctype(settings_doctype, starter.theme_settings, self.module).insert()
			self.db_set("theme_settings", settings_doctype)

	def get_starter(self):
		if self.parent_theme:
			return None
		return get_starter_theme(self.theme_type)

	@frappe.whitelist(methods=["POST"])
	def scaffold_theme_settings(self):
		self.check_permission("write")

		settings_doctype = f"{self.theme_name} Settings"
		if frappe.db.exists("DocType", settings_doctype):
			frappe.throw(frappe._("DocType {0} already exists").format(settings_doctype))

		frappe.enqueue_doc(self.doctype, self.name, "create_theme_settings", enqueue_after_commit=True)
		return settings_doctype

	def create_theme_settings(self):
		settings_doctype = f"{self.theme_name} Settings"
		create_theme_settings_doctype(settings_doctype, self.module)
		self.db_set("theme_settings", settings_doctype, notify=True)

	def after_rename(self, old_name, new_name, merge=False):
		validate_theme_name(old_name)
		validate_theme_name(new_name)

		old_slug = frappe.scrub(old_name)
		new_slug = frappe.scrub(new_name)

		if old_slug != new_slug:
			app_path = frappe.get_app_path(get_app_for_module(self.module))
			for base_dir in (
				os.path.join(app_path, "themes"),
				os.path.join(app_path, "public", "themes"),
			):
				old_path = get_contained_path(base_dir, old_slug)
				new_path = get_contained_path(base_dir, new_slug)
				if os.path.isdir(old_path):
					os.rename(old_path, new_path)

			if self.module and frappe.conf.developer_mode:
				rename_theme_export_dir(self.module, old_slug, new_slug)

		self.db_set("theme_name", new_name)

		if frappe.conf.developer_mode and self.is_standard and self.module:
			self.theme_name = new_name
			export_module_json(self, is_standard=True, module=self.module)

	def on_update(self):
		if not frappe.conf.developer_mode:
			return

		doc_before = self.get_doc_before_save()
		if doc_before and not any(self.get(field) != doc_before.get(field) for field in EXPORTED_FIELDS):
			return

		export_module_json(self, is_standard=bool(self.is_standard), module=self.module)

	def on_change(self):
		clear_theme_cache()

	def on_trash(self):
		# A standard theme's folders are app source; deleting the record must never rmtree them.
		if not frappe.conf.developer_mode or self.is_standard:
			return

		validate_theme_name(self.name)
		paths = [get_theme_dir(self.name), get_theme_public_dir(self.name)]
		if self.module:
			paths.append(get_theme_export_dir(self.module, frappe.scrub(self.name)))
		for path in paths:
			if os.path.isdir(path):
				shutil.rmtree(path)

	def validate_no_circular_inheritance(self):
		visited = {self.name}
		current = self.parent_theme
		while current:
			if current in visited:
				frappe.throw(frappe._("Circular theme inheritance detected: {0}").format(current))
			visited.add(current)
			current = frappe.db.get_value("Shop Theme", current, "parent_theme")

	def validate_parent_theme_type(self):
		if self.parent_theme == BASE_THEME:
			return
		parent_theme_type = frappe.db.get_value("Shop Theme", self.parent_theme, "theme_type")
		if parent_theme_type != self.theme_type:
			frappe.throw(
				frappe._("{0} is a {1} theme. A {2} theme can only inherit from a {2} theme.").format(
					self.parent_theme, parent_theme_type, self.theme_type
				)
			)


EXPORTED_FIELDS = (
	"theme_name",
	"theme_type",
	"parent_theme",
	"config",
	"is_standard",
	"module",
	"theme_settings",
)


def validate_theme_name(theme_name):
	if not THEME_NAME_PATTERN.match(theme_name or ""):
		frappe.throw(
			frappe._("Theme name may only contain letters, numbers, spaces, hyphens and underscores")
		)


def is_within_directory(directory, target):
	directory = os.path.realpath(directory)
	target = os.path.realpath(target)
	# The trailing separator rejects the sibling-prefix case: /themes/foo_evil is not inside /themes/foo.
	return target == directory or target.startswith(directory + os.sep)


def get_contained_path(base_dir, *segments):
	path = os.path.join(base_dir, *segments)
	if not is_within_directory(base_dir, path):
		frappe.throw(frappe._("Invalid theme path: {0}").format(path))
	return path


def get_app_for_module(module):
	app = frappe.db.get_value("Module Def", module, "app_name") if module else None
	return app or DEFAULT_THEME_APP


def get_theme_app(theme_name):
	return get_app_for_module(frappe.db.get_value("Shop Theme", theme_name, "module"))


def get_theme_dir(theme_name):
	base_dir = os.path.join(frappe.get_app_path(get_theme_app(theme_name)), "themes")
	return get_contained_path(base_dir, frappe.scrub(theme_name))


def get_theme_public_dir(theme_name):
	base_dir = os.path.join(frappe.get_app_path(get_theme_app(theme_name)), "public", "themes")
	return get_contained_path(base_dir, frappe.scrub(theme_name))


def get_theme_export_dir(module, slug):
	return get_contained_path(frappe.get_module_path(module), "shop_theme", slug)


def rename_theme_export_dir(module, old_slug, new_slug):
	old_export_dir = get_theme_export_dir(module, old_slug)
	new_export_dir = get_theme_export_dir(module, new_slug)
	if os.path.isdir(old_export_dir):
		os.rename(old_export_dir, new_export_dir)
	if not os.path.isdir(new_export_dir):
		return

	for filename in os.listdir(new_export_dir):
		if filename.endswith(".json") and filename != f"{new_slug}.json":
			os.remove(os.path.join(new_export_dir, filename))


def create_theme_settings_doctype(doctype_name, module=None):
	permissions = [
		{
			"role": role,
			"read": 1,
			"write": 1,
			"create": 1,
			"delete": 1,
			"share": 1,
			"print": 1,
			"email": 1,
			"report": 0,
			"export": 0,
		}
		for role in ("System Manager", "Website Manager")
	]
	doctype = frappe.new_doc("DocType")
	doctype.update(
		{
			"name": doctype_name,
			"module": module or DEFAULT_THEME_MODULE,
			"custom": 0 if frappe.conf.developer_mode else 1,
			"issingle": 1,
			"fields": [
				{"fieldname": "info_section", "fieldtype": "Section Break", "label": "Theme Settings"},
				{"fieldname": STYLE_TAB, "fieldtype": "Tab Break", "label": "Style"},
			],
			"permissions": permissions,
		}
	)
	doctype.insert()
	return doctype


def get_starter_theme(theme_type):
	return frappe.db.get_value(
		"Shop Theme",
		{"use_as_starter": 1, "theme_type": theme_type},
		["name", "module", "theme_settings"],
		as_dict=True,
	)


def copy_starter_settings_doctype(doctype_name, starter_settings, module=None):
	doctype = frappe.copy_doc(frappe.get_doc("DocType", starter_settings))
	doctype.update(
		{
			"name": doctype_name,
			"module": module or DEFAULT_THEME_MODULE,
			"custom": 0 if frappe.conf.developer_mode else 1,
		}
	)
	return doctype


def scaffold_theme(theme_name, module=None, theme_type="Classic", app=None, parent_theme=None):
	app_path = Path(frappe.get_app_path(app or get_app_for_module(module)))
	slug = frappe.scrub(theme_name)
	theme_dir = Path(get_contained_path(app_path / "themes", slug))
	if theme_dir.exists():
		return [("skipped", str(theme_dir.relative_to(app_path.parent)))]

	starter = None if parent_theme else get_starter_theme(theme_type)
	if starter:
		return [
			("created", str(target_dir.relative_to(app_path.parent)))
			for target_dir in copy_starter_theme(theme_name, app_path, starter)
		]

	for folder in THEME_FOLDERS[theme_type]:
		(theme_dir / folder).mkdir(parents=True, exist_ok=True)

	# A real directory, never a symlink to the private tree: .py controllers must stay unreachable over HTTP.
	theme_public_dir = Path(get_contained_path(app_path / "public" / "themes", slug))
	for folder in ("scripts", "images"):
		(theme_public_dir / folder).mkdir(parents=True, exist_ok=True)

	starter_dirs = [THEME_STARTER_DIR / theme_type.lower()]
	# A child theme renders with its parent's components/base.html.
	if not parent_theme:
		starter_dirs.append(THEME_STARTER_DIR / "standalone")
	changes = []
	for starter_dir in starter_dirs:
		changes.extend(write_minimal_starter(starter_dir, theme_dir, theme_name, app_path))
	return changes


def write_minimal_starter(starter_dir, theme_dir, theme_name, app_path):
	changes = []
	for starter in sorted(path for path in starter_dir.rglob("*") if path.is_file()):
		path = theme_dir / starter.relative_to(starter_dir)
		path.parent.mkdir(parents=True, exist_ok=True)
		# nosemgrep: frappe-direct-jinja-construction
		path.write_text(Template(starter.read_text()).safe_substitute(theme_name=theme_name))
		changes.append(("created", str(path.relative_to(app_path.parent))))
	return changes


def copy_starter_theme(theme_name, app_path, starter):
	starter_app_path = Path(frappe.get_app_path(get_app_for_module(starter.module)))
	starter_slug = frappe.scrub(starter.name)
	slug = frappe.scrub(theme_name)
	copies = [
		(starter_app_path / base_dir / starter_slug, Path(get_contained_path(app_path / base_dir, slug)))
		for base_dir in ("themes", "public/themes")
	]
	for source_dir, target_dir in copies:
		shutil.copytree(
			source_dir,
			target_dir,
			ignore=shutil.ignore_patterns("__pycache__", "node_modules"),
			dirs_exist_ok=True,
		)
		for path in target_dir.rglob("*"):
			if path.suffix not in STARTER_TEXT_SUFFIXES or not path.is_file():
				continue
			text = path.read_text()
			renamed = text.replace(starter.name, theme_name).replace(starter_slug, slug)
			if renamed != text:
				path.write_text(renamed)
	return [target_dir for source_dir, target_dir in copies]


def get_theme_names(theme_name):
	"""The inheritance chain child-first, cycle-guarded."""
	names = []
	visited = set()
	current = theme_name
	while current and current not in visited:
		visited.add(current)
		names.append(current)
		current = frappe.db.get_value("Shop Theme", current, "parent_theme")
	return names


def build_theme_context(theme_name):
	if not theme_name:
		return {
			"theme_name": None,
			"theme_type": None,
			"names": [],
			"dirs": [],
			"apps": {},
			"settings_doctype": None,
		}

	names = get_theme_names(theme_name)
	apps = {}
	dirs = []
	for name in names:
		app = get_theme_app(name)
		apps[name] = app
		theme_dir = os.path.join(frappe.get_app_path(app), "themes", frappe.scrub(name))
		if os.path.isdir(theme_dir):
			dirs.append(theme_dir)

	return {
		"theme_name": theme_name,
		"theme_type": frappe.db.get_value("Shop Theme", theme_name, "theme_type"),
		"names": names,
		"dirs": dirs,
		"apps": apps,
		"settings_doctype": find_theme_settings_doctype(names),
	}


def find_theme_settings_doctype(theme_names):
	settings_by_theme = dict(
		frappe.get_all(
			"Shop Theme",
			filters={"name": ("in", theme_names), "theme_settings": ("is", "set")},
			fields=["name", "theme_settings"],
			as_list=True,
		)
	)
	if not settings_by_theme:
		return None

	installed = set(
		frappe.get_all("DocType", filters={"name": ("in", list(settings_by_theme.values()))}, pluck="name")
	)
	for name in theme_names:
		if settings_by_theme.get(name) in installed:
			return settings_by_theme[name]
	return None


def get_theme_context(theme_name):
	if not theme_name:
		return build_theme_context(None)
	return frappe.cache.hget(
		THEME_CONTEXT_CACHE_KEY, theme_name, generator=lambda: build_theme_context(theme_name)
	)


def resolve_active_theme():
	try:
		return frappe.get_cached_doc("Shop Theme Settings").active_theme
	except frappe.DoesNotExistError:
		# The doctype does not exist yet during the first migrate that installs it.
		return None


def resolve_theme():
	return requested_preview_theme() or resolve_active_theme()


RENDER_THEME_CONTEXT_LOCAL_KEY = "shop_theme_render_context"


def get_render_theme_context():
	context = getattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, None)
	if context is None:
		context = get_theme_context(resolve_theme())
		setattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, context)
	return context


def clear_render_theme_context():
	setattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, None)


@contextmanager
def render_theme_context(theme_context):
	"""Pin shop_theme_asset_url() and shop_theme_config() to one theme for the duration, so previewing
	a non-live theme cannot hand its templates the LIVE theme's asset URLs and settings Single."""
	previous = getattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, None)
	setattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, theme_context)
	try:
		yield
	finally:
		setattr(frappe.local, RENDER_THEME_CONTEXT_LOCAL_KEY, previous)


def requested_preview_theme():
	if not frappe.conf.developer_mode:
		return None

	request = getattr(frappe.local, "request", None)
	if not request:
		return None

	theme_name = request.args.get(PREVIEW_THEME_PARAM)
	if not theme_name or not frappe.db.exists("Shop Theme", theme_name):
		return None

	return theme_name


def clear_theme_cache():
	frappe.cache.delete_value(THEME_CONTEXT_CACHE_KEY)
	clear_render_theme_context()
