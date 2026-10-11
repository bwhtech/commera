import ast
import json
import random
from pathlib import Path
from string import Template

import click

from commera.plugins.places import NAME_PATTERN, PLACES
from commera.sdk import API_VERSION

COMMERA_ROOT = Path(__file__).parents[2]
STARTER_DIR = Path(__file__).parent / "starter"
STARTER_ICON = "sparkles"
SHARED_PACKAGES = ("@vitejs/plugin-vue", "vite", "vue")
# frappe-ui's violet, orange, blue and green 500 shades; a new plugin's placeholder logo gets one at random.
LOGO_COLOURS = ("#7757EE", "#E86C13", "#0C8EF8", "#43AC79")
# What `bench commera add` takes, mapped to the placement folder it writes and the starter it writes there.
PLACE_KINDS = {
	"page": ("pages", "page"),
	"order-card": ("order/cards", "card"),
	"product-card": ("product/cards", "card"),
	"customer-card": ("customer/cards", "card"),
	"order-action": ("order/actions", "action"),
	"product-action": ("product/actions", "action"),
	"customer-action": ("customer/actions", "action"),
	"settings": ("settings", "settings"),
	"command": ("commands", "command"),
}


class AppScaffold:
	def __init__(self, app: str, apps_path: Path):
		if app == "commera":
			raise click.ClickException("commera is the host app; run this inside the app that extends it")
		self.app = app
		self.app_root = Path(apps_path) / app
		self.hooks_path = self.app_root / app / "hooks.py"
		if not self.hooks_path.is_file():
			raise click.ClickException(
				f"{app} is not a Frappe app in {apps_path}; create it with bench new-app"
			)
		self.source_dir = self.app_root / "commera"
		self.changes: list[tuple[str, str]] = []

	def save(self) -> list[tuple[str, str]]:
		self.add_hooks()
		self.add_package_json()
		self.add_gitignore_lines(["node_modules", f"{self.app}/public/commera/"])
		self.add_file(self.app_root / self.app / "public" / ".gitkeep", "")
		self.add_file(self.source_dir / "vite.config.js", get_starter("vite.config.js"))
		self.add_file(
			self.source_dir / "plugin-icon.svg",
			Template(get_starter("plugin-icon.svg")).substitute(colour=random.choice(LOGO_COLOURS)),
		)
		self.add_places()
		# A plain api.py here would be importable, and so callable, as commera.scaffold.starter.api.
		self.add_file(self.app_root / self.app / "api.py", get_starter("api.py.template"))
		self.add_file(self.source_dir / "README.md", self.format_starter("README.md"))
		return self.changes

	def add_hooks(self):
		text = self.hooks_path.read_text()
		updated = add_assignment(
			set_required_apps(text), "commera_api_version", f"[{API_VERSION}]", "required_apps"
		)
		updated = add_assignment(
			updated, "commera_plugin_title", json.dumps(self.get_app_title()), "commera_api_version"
		)
		self.write_change(self.hooks_path, updated, text != updated)

	def add_package_json(self):
		path = self.app_root / "package.json"
		package = json.loads(path.read_text()) if path.exists() else {"name": self.app, "private": True}
		original = json.dumps(package)
		package.setdefault("type", "module")
		scripts = package.setdefault("scripts", {})
		scripts.setdefault("build", "vite build --config commera/vite.config.js")
		dev_dependencies = package.setdefault("devDependencies", {})
		dev_dependencies.setdefault("@commera/plugin-kit", "link:../commera/packages/plugin-kit")
		for name, version in get_dashboard_versions().items():
			dev_dependencies.setdefault(name, version)
		self.write_change(path, json.dumps(package, indent="\t") + "\n", json.dumps(package) != original)

	def add_gitignore_lines(self, wanted: list[str]):
		path = self.app_root / ".gitignore"
		text = path.read_text() if path.exists() else ""
		present = {line.strip() for line in text.splitlines()}
		missing = [line for line in wanted if line not in present]
		if text and not text.endswith("\n"):
			text += "\n"
		self.write_change(path, text + "".join(f"{line}\n" for line in missing), bool(missing))

	def add_places(self):
		for place in PLACES:
			if (self.source_dir / place).exists():
				self.changes.append(("skipped", f"commera/{place}/"))
			elif place == "pages":
				self.add_file(
					self.source_dir / place / self.page_name / "index.vue", self.format_starter("page.vue")
				)
			else:
				self.add_file(self.source_dir / place / ".gitkeep", "")

	def add_file(self, path: Path, content: str):
		self.write_change(path, content, not path.exists())

	def write_change(self, path: Path, content: str, changed: bool):
		if not changed:
			self.changes.append(("skipped", self.get_relative_path(path)))
			return
		self.changes.append(("updated" if path.exists() else "created", self.get_relative_path(path)))
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content)

	def add_place(self, kind: str, name: str | None, detail: bool = False) -> list[tuple[str, str]]:
		if kind not in PLACE_KINDS:
			raise click.ClickException(f"Add one of: {', '.join(PLACE_KINDS)}")
		place, starter = PLACE_KINDS[kind]
		if detail and kind != "page":
			raise click.ClickException(
				"--detail only goes with a page: bench commera add page <name> --detail"
			)
		if place == "settings":
			folder = Path("settings")
			label = "Settings"
		else:
			if not name or not NAME_PATTERN.fullmatch(name):
				raise click.ClickException(
					f"Give the {kind} a name of lowercase letters, digits and hyphens: bench commera add {kind} <name>"
				)
			folder = Path(place) / name
			label = name.replace("-", " ").capitalize()
		if (self.source_dir / folder / "index.vue").exists():
			raise click.ClickException(f"commera/{folder} already exists; pick another name")

		doctype = PLACES[place]["doctype"]
		record = place.split("/")[0]
		function = get_function_name(name or "", record if doctype else None)
		values = {
			"app_name": self.app,
			"name": name or "",
			"label": label,
			"folder": folder.as_posix(),
			"function": function,
			"doctype": doctype or "",
			"record": record,
		}
		self.add_file(
			self.source_dir / folder / "index.vue",
			Template(get_starter(f"places/{'page_with_detail' if detail else starter}.vue")).substitute(
				values
			),
		)
		if detail:
			self.add_file(
				self.source_dir / folder / "[...id].vue",
				Template(get_starter("places/detail.vue")).substitute(values),
			)
		if starter in ("action", "command"):
			self.add_api_method(
				function, Template(get_starter(f"places/{starter}.py.template")).substitute(values)
			)
		return self.changes

	def add_api_method(self, function: str, source: str):
		path = self.app_root / self.app / "api.py"
		text = path.read_text() if path.exists() else "import frappe\n"
		if function in {node.name for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}:
			raise click.ClickException(f"{self.app}/api.py already has {function}; pick another name")
		self.write_change(path, text.rstrip("\n") + "\n" + source, True)

	def format_starter(self, name: str) -> str:
		label = self.get_app_title().replace("\\", "\\\\").replace("'", "\\'")
		return Template(get_starter(name)).safe_substitute(
			app_name=self.app, label=label, page_name=self.page_name, icon=STARTER_ICON
		)

	@property
	def page_name(self) -> str:
		name = self.app.replace("_", "-")[:40].strip("-")
		return name if NAME_PATTERN.fullmatch(name) else "home"

	def get_app_title(self) -> str:
		assignment = get_assignments(self.hooks_path.read_text()).get("app_title")
		if (
			assignment
			and isinstance(assignment.value, ast.Constant)
			and isinstance(assignment.value.value, str)
		):
			return assignment.value.value
		return self.app.replace("_", " ").title()

	def get_relative_path(self, path: Path) -> str:
		return str(path.relative_to(self.app_root))


def get_function_name(name: str, record: str | None) -> str:
	function = name.replace("-", "_")
	if record:
		function = f"{function}_{record}"
	return function if function[:1].isalpha() else f"run_{function}"


def get_app_from_folder(folder: Path, apps_path: Path) -> str:
	try:
		app = Path(folder).resolve().relative_to(Path(apps_path).resolve()).parts[0]
	except (ValueError, IndexError):
		raise click.ClickException("Run bench commera inside your app's folder: cd apps/<your_app>")
	return app


def get_starter(name: str) -> str:
	return (STARTER_DIR / name).read_text()


def get_dashboard_versions() -> dict[str, str]:
	package = json.loads((COMMERA_ROOT / "dashboard" / "package.json").read_text())
	versions = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
	return {name: versions[name] for name in SHARED_PACKAGES}


def get_assignments(text: str) -> dict[str, ast.Assign]:
	return {
		node.targets[0].id: node
		for node in ast.parse(text).body
		if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
	}


def set_required_apps(text: str) -> str:
	lines = text.splitlines(keepends=True)
	assignment = get_assignments(text).get("required_apps")
	if not assignment:
		statement = 'required_apps = ["commera"]\n'
		for index, line in enumerate(lines):
			if line.strip() == "# required_apps = []":
				lines[index] = statement
				return "".join(lines)
		return insert_after(lines, get_metadata_end(text), statement)

	try:
		apps = ast.literal_eval(assignment.value)
	except ValueError:
		apps = None
	if not isinstance(apps, list | tuple):
		raise click.ClickException("required_apps in hooks.py is not a plain list; add commera to it by hand")
	if "commera" in apps:
		return text
	lines[assignment.lineno - 1 : assignment.end_lineno] = [
		f"required_apps = {json.dumps([*apps, 'commera'])}\n"
	]
	return "".join(lines)


def add_assignment(text: str, name: str, literal: str, after: str) -> str:
	assignments = get_assignments(text)
	if name in assignments:
		return text
	return insert_after(
		text.splitlines(keepends=True), assignments[after].end_lineno, f"{name} = {literal}\n"
	)


def get_metadata_end(text: str) -> int:
	metadata = [node.end_lineno for name, node in get_assignments(text).items() if name.startswith("app_")]
	return max(metadata, default=len(text.splitlines()))


def insert_after(lines: list[str], line_number: int, statement: str) -> str:
	if line_number and not lines[line_number - 1].endswith("\n"):
		lines[line_number - 1] += "\n"
	lines.insert(line_number, statement)
	return "".join(lines)
