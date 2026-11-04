import keyword
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import click
import frappe
from frappe import scrub
from frappe.utils.boilerplate import _create_app_boilerplate
from frappe.utils.change_log import get_app_branch

from commera.payment_gateways.connectors import KIND
from commera.scaffold import COMMERA_ROOT, AppScaffold, get_app_from_folder

LABEL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 ]{0,60}")
APP_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
LIBRARY = "bwh_payments_core"
LIBRARY_DISTRIBUTION = "bwh-payments-core"
COMMERA_DOCTYPES = COMMERA_ROOT / "commera" / "payment_gateways" / "doctype"
LIBRARY_IMPORTS = (
	f"from {LIBRARY}.contract import PaymentGatewayBase",
	f"from {LIBRARY}.currency import to_minor_units, validate_transaction_currency",
	f"from {LIBRARY}.models import CheckoutSession, RefundResult, WebhookEvent",
)
TRANSLATE_IMPORT = "from frappe import _"
NEW_APP_EMAIL = "developer@example.com"


class PaymentGatewayScaffold(AppScaffold):
	@property
	def next_step(self) -> str:
		return (
			f"Next: point {self.app}/connectors/<gateway>/live.py at the real API, then bench --site <site> "
			f"install-app {self.app} (or migrate, if it is already installed)."
		)

	def add_payment_gateway(self, label: str) -> list[tuple[str, str]]:
		values = {**self.get_values(label), "module": self.get_module()}
		doctype = values["doctype"]
		if (COMMERA_DOCTYPES / scrub(doctype)).exists():
			raise click.ClickException(f"Commera already ships {doctype}; pick another name")

		self.add_connector(values)
		folder = self.app_root / self.app / scrub(values["module"]) / "doctype" / scrub(doctype)
		self.add_file(folder / "__init__.py", "")
		for suffix in ("json", "py"):
			self.add_file(
				folder / f"{scrub(doctype)}.{suffix}",
				self.format_starter(f"payment_gateway/settings.{suffix}.template", **values),
			)
		self.add_provider_hooks(doctype, KIND)
		return self.changes

	def add_to_bench(self):
		apps_txt = self.app_root.parents[1] / "sites" / "apps.txt"
		text = apps_txt.read_text()
		if self.app not in text.split():
			self.install_packages((sys.executable, "-m", "pip", "install", "--quiet", "-e", "."))
			apps_txt.write_text(f"{text.rstrip()}\n{self.app}\n")

	def get_values(self, label: str) -> dict[str, str]:
		label = " ".join(label.split())
		slug = scrub(label)
		return {
			"label": label,
			"slug": slug,
			"prefix": label.replace(" ", ""),
			"doctype": f"{label} Gateway Settings",
			"package": f"{self.app}.connectors.{slug}",
			"timestamp": str(datetime.now()),
		}

	def add_connector(self, values: dict[str, str]):
		values = {**values, "imports": self.format_gateway_imports(values)}
		connectors = self.app_root / self.app / "connectors"
		self.add_file(connectors / "__init__.py", "")
		folder = connectors / values["slug"]
		self.add_file(folder / "__init__.py", "")
		for name in ("gateway", "base", "live", "stub"):
			self.add_file(
				folder / f"{name}.py", self.format_starter(f"payment_gateway/{name}.py.template", **values)
			)
		self.add_file(
			self.get_test_path(values["slug"]),
			self.format_starter("payment_gateway/test_gateway.py.template", **values),
		)

	def get_test_path(self, slug: str) -> Path:
		return self.app_root / self.app / "connectors" / slug / f"test_{slug}.py"

	def format_gateway_imports(self, values: dict[str, str]) -> str:
		third_party = sorted((TRANSLATE_IMPORT, *LIBRARY_IMPORTS))
		return "\n".join(third_party) + "\n\n" + "\n".join(get_connector_imports(values))


class LibraryConnectorScaffold(PaymentGatewayScaffold):
	def __init__(self, root: Path):
		self.app = LIBRARY
		self.app_root = root
		self.changes: list[tuple[str, str]] = []

	@property
	def next_step(self) -> str:
		return f"Next: point {LIBRARY}/connectors/<gateway>/live.py at the real API, then run pytest."

	def add_payment_gateway(self, label: str) -> list[tuple[str, str]]:
		self.add_connector(self.get_values(label))
		return self.changes

	def get_app_title(self) -> str:
		return LIBRARY

	def get_test_path(self, slug: str) -> Path:
		return self.app_root / "tests" / f"test_{slug}.py"

	def format_gateway_imports(self, values: dict[str, str]) -> str:
		first_party = sorted((*LIBRARY_IMPORTS, *get_connector_imports(values)))
		return TRANSLATE_IMPORT + "\n\n" + "\n".join(first_party)


def get_payment_gateway_scaffold(
	label: str, folder: Path, apps_path: Path, app: str | None = None, app_name: str | None = None
) -> PaymentGatewayScaffold:
	validate_label(label)
	library_root = get_library_root(folder)
	current_app = get_current_app(folder, apps_path)
	if app_name and (app or library_root or current_app):
		raise click.ClickException("--app-name names a new app, so run it outside any app")

	if app:
		return PaymentGatewayScaffold(app, apps_path)
	if library_root:
		return LibraryConnectorScaffold(library_root)
	if current_app:
		return PaymentGatewayScaffold(current_app, apps_path)

	app_name = app_name or f"commera_{scrub(' '.join(label.split()))}"
	add_app(app_name, apps_path)
	scaffold = PaymentGatewayScaffold(app_name, apps_path)
	scaffold.add_to_bench()
	return scaffold


def validate_label(label: str):
	label = " ".join(label.split())
	if not LABEL_PATTERN.fullmatch(label) or keyword.iskeyword(scrub(label)):
		raise click.ClickException(
			"Name the gateway with letters, digits and spaces, such as Tamara, and not a Python keyword"
		)


def get_library_root(folder: Path) -> Path | None:
	for parent in (folder, *folder.parents):
		pyproject = parent / "pyproject.toml"
		if (
			pyproject.is_file()
			and tomllib.loads(pyproject.read_text()).get("project", {}).get("name") == LIBRARY_DISTRIBUTION
		):
			return parent
	return None


def get_current_app(folder: Path, apps_path: Path) -> str | None:
	try:
		return get_app_from_folder(folder, apps_path)
	except click.ClickException:
		return None


def add_app(app: str, apps_path: Path):
	if not APP_NAME_PATTERN.fullmatch(app) or keyword.iskeyword(app):
		raise click.ClickException("Name the app with lowercase letters, digits and underscores")

	if not (apps_path / app).exists():
		title = app.replace("_", " ").title()
		hooks = frappe._dict(
			app_name=app,
			app_title=title,
			app_description=f"{title} payment gateway for Commera",
			app_publisher=title,
			app_email=NEW_APP_EMAIL,
			app_license="mit",
			create_github_workflow=False,
			branch_name=get_new_app_branch(),
		)
		_create_app_boilerplate(str(apps_path), hooks)


def get_new_app_branch() -> str:
	branch = get_app_branch("frappe")
	return "develop" if branch in ("", "HEAD") else branch


def get_connector_imports(values: dict[str, str]) -> list[str]:
	package, prefix = values["package"], values["prefix"]
	return [
		f"from {package}.base import Base{prefix}Client",
		f"from {package}.live import Live{prefix}Client",
		f"from {package}.stub import Stub{prefix}Client",
	]
