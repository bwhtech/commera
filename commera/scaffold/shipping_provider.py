import ast
import json
import re
from string import Template

import click
from frappe.utils import now, scrub

from commera.scaffold import AppScaffold, add_assignment, get_assignments, get_starter, set_required_apps
from commera.sdk import API_VERSION
from commera.shipping.providers import KIND

LABEL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 ]{0,60}")


class ShippingProviderScaffold(AppScaffold):
	def add_shipping_provider(self, label: str) -> list[tuple[str, str]]:
		"""Write a carrier's settings Single and register it, ready for `bench migrate`."""
		label = label.strip()
		if not LABEL_PATTERN.fullmatch(label):
			raise click.ClickException("Name the carrier with letters, digits and spaces, such as Delhivery")

		doctype = f"{label} Shipping Settings"
		module = self.get_module()
		folder = self.app_root / self.app / scrub(module) / "doctype" / scrub(doctype)
		if folder.exists():
			raise click.ClickException(f"{doctype} already exists in {self.app}")

		values = {
			"doctype": doctype,
			"module": module,
			"label": label,
			"class_name": doctype.replace(" ", ""),
			"timestamp": now(),
		}
		self.add_file(folder / "__init__.py", "")
		for suffix in ("json", "py"):
			self.add_file(
				folder / f"{scrub(doctype)}.{suffix}",
				# nosemgrep: frappe-direct-jinja-construction
				Template(get_starter(f"shipping_provider/settings.{suffix}.template")).substitute(values),
			)
		self.add_provider_hooks(doctype)
		return self.changes

	def get_module(self) -> str:
		modules = (self.app_root / self.app / "modules.txt").read_text().split("\n")
		return next(module.strip() for module in modules if module.strip())

	def add_provider_hooks(self, doctype: str):
		text = self.hooks_path.read_text()
		updated = add_assignment(
			set_required_apps(text), "commera_api_version", f"[{API_VERSION}]", "required_apps"
		)
		updated = add_hook_entry(updated, "commera_hooks", KIND, doctype)
		self.write_change(self.hooks_path, updated, text != updated)


def add_hook_entry(text: str, hook: str, key: str, value: str) -> str:
	assignment = get_assignments(text).get(hook)
	if not assignment:
		return add_assignment(text, hook, json.dumps({key: [value]}), "commera_api_version")

	try:
		hooks = ast.literal_eval(assignment.value)
	except ValueError:
		hooks = None
	if not isinstance(hooks, dict):
		raise click.ClickException(
			f"{hook} in hooks.py is not a plain dict; add {value} to {hook}[{key!r}] by hand"
		)
	if value in hooks.get(key, []):
		return text

	hooks[key] = [*hooks.get(key, []), value]
	lines = text.splitlines(keepends=True)
	lines[assignment.lineno - 1 : assignment.end_lineno] = [f"{hook} = {json.dumps(hooks)}\n"]
	return "".join(lines)
