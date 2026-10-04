import ast
import json
from pathlib import Path
from string import Template

import click

from commera.extensions.places import NAME_PATTERN, PLACES
from commera.sdk import API_VERSION

COMMERA_ROOT = Path(__file__).parents[2]
STARTER_DIR = Path(__file__).parent / "starter"
STARTER_ICON = "sparkles"
SHARED_PACKAGES = ("@vitejs/plugin-vue", "vite", "vue")


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
		self.add_places()
		# A plain api.py here would be importable, and so callable, as commera.scaffold.starter.api.
		self.add_file(self.app_root / self.app / "api.py", get_starter("api.py.template"))
		self.add_file(self.source_dir / "README.md", self.format_starter("README.md"))
		return self.changes

	def add_hooks(self):
		text = self.hooks_path.read_text()
		updated = set_commera_api_version(set_required_apps(text))
		self.write_change(self.hooks_path, updated, text != updated)

	def add_package_json(self):
		path = self.app_root / "package.json"
		package = json.loads(path.read_text()) if path.exists() else {"name": self.app, "private": True}
		original = json.dumps(package)
		package.setdefault("type", "module")
		scripts = package.setdefault("scripts", {})
		scripts.setdefault("build", "vite build --config commera/vite.config.js")
		scripts.setdefault("dev", "vite build --watch --config commera/vite.config.js")
		dev_dependencies = package.setdefault("devDependencies", {})
		dev_dependencies.setdefault("@commera/extension-kit", "link:../commera/packages/extension-kit")
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
		if path.exists():
			self.changes.append(("skipped", self.get_relative_path(path)))
			return
		self.write_change(path, content, True)

	def write_change(self, path: Path, content: str, changed: bool):
		if not changed:
			self.changes.append(("skipped", self.get_relative_path(path)))
			return
		self.changes.append(("updated" if path.exists() else "created", self.get_relative_path(path)))
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content)

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


def get_app_from_folder(folder: Path, apps_path: Path) -> str:
	try:
		app = Path(folder).resolve().relative_to(Path(apps_path).resolve()).parts[0]
	except (ValueError, IndexError):
		raise click.ClickException("Run bench commera init inside your app's folder: cd apps/<your_app>")
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


def set_commera_api_version(text: str) -> str:
	assignments = get_assignments(text)
	if "commera_api_version" in assignments:
		return text
	statement = f"commera_api_version = [{API_VERSION}]\n"
	return insert_after(text.splitlines(keepends=True), assignments["required_apps"].end_lineno, statement)


def get_metadata_end(text: str) -> int:
	metadata = [node.end_lineno for name, node in get_assignments(text).items() if name.startswith("app_")]
	return max(metadata, default=len(text.splitlines()))


def insert_after(lines: list[str], line_number: int, statement: str) -> str:
	if line_number and not lines[line_number - 1].endswith("\n"):
		lines[line_number - 1] += "\n"
	lines.insert(line_number, statement)
	return "".join(lines)
