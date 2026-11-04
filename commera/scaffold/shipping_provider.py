import re
from string import Template

import click
from frappe import scrub
from frappe.utils import now

from commera.scaffold import AppScaffold, get_starter
from commera.shipping.providers import KIND

LABEL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 ]{0,60}")


class ShippingProviderScaffold(AppScaffold):
	def add_shipping_provider(self, label: str) -> list[tuple[str, str]]:
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
		self.add_provider_hooks(doctype, KIND)
		return self.changes
