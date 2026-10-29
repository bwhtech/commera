import os
from pathlib import Path

import click
from frappe.commands import get_site, pass_context


@click.group("commera")
def commera_commands():
	"""Commera tools for plugins that extend the Commera dashboard."""


# Run from the bench folder, bench skips the app name "commera" and runs its own `bench init` instead.
@commera_commands.command("init")
@click.option("--skip-install", is_flag=True, default=False, help="Do not run yarn install in the app")
def init(skip_install: bool):
	"""Set up the app you are in as a Commera plugin that adds pages, cards, actions and settings to the Commera dashboard."""
	scaffold = get_current_app_scaffold()
	for change, path in scaffold.save(install=not skip_install):
		click.echo(f"{change:<8} {path}")

	click.secho("Next: run yarn dev in apps/commera/dashboard, then open /commera on port 8080", fg="green")
	click.echo(f"For production: bench build --app {scaffold.app}")


@commera_commands.command("add")
@click.argument("kind")
@click.argument("name", required=False)
@click.option(
	"--detail", is_flag=True, default=False, help="With a page, also add [...id].vue for one record's view"
)
def add(kind: str, name: str | None, detail: bool):
	"""Add one starter placement to the plugin you are in: page, order-card, product-card, customer-card,
	order-action, product-action, customer-action, settings or command."""
	scaffold = get_current_app_scaffold()
	for change, path in scaffold.add_place(kind, name, detail):
		click.echo(f"{change:<8} {path}")
	click.secho(
		"A running yarn dev in apps/commera/dashboard picks it up; otherwise run bench build --app "
		+ scaffold.app,
		fg="green",
	)


@commera_commands.group("theme")
def theme():
	"""Storefront themes in the app you are in."""


@theme.command("new")
@click.argument("name")
@click.option(
	"--type",
	"theme_type",
	type=click.Choice(["sections", "classic"]),
	required=True,
	help="sections: pages built from sections/ and layouts/; classic: hardcoded pages/ and components/",
)
@click.option(
	"--parent",
	default="Shop Base Theme",
	show_default=True,
	help="Shop Theme to inherit from: Shop Base Theme or one of the same type",
)
@click.option("--app", help="App to add the theme to, instead of the app you are in")
@pass_context
def new_theme(context, name: str, theme_type: str, parent: str, app: str | None):
	"""Add a storefront theme to an app and create its Shop Theme record."""
	import frappe

	from commera.scaffold.theme import ThemeScaffold

	scaffold = get_current_app_scaffold(ThemeScaffold, app)
	site = get_site(context)
	frappe.init(site)
	frappe.connect()
	try:
		installed = scaffold.is_installed()
		for change, path in scaffold.add_theme(name, theme_type.title(), parent):
			click.echo(f"{change:<8} {path}")
		frappe.db.commit()  # nosemgrep
	finally:
		frappe.destroy()

	if installed:
		click.secho(f"Next: set Active Theme to {name} in Shop Theme Settings, then open /en", fg="green")
	else:
		click.secho(
			f"Next: bench --site {site} install-app {scaffold.app} creates the Shop Theme record", fg="green"
		)


@commera_commands.group("shipping-provider")
def shipping_provider():
	"""Shipping carriers in the app you are in."""


@shipping_provider.command("new")
@click.argument("label")
@click.option("--app", help="App to add the carrier to, instead of the app you are in")
def new_shipping_provider(label: str, app: str | None):
	"""Add a carrier's settings DocType to an app and register it in commera_hooks."""
	from commera.scaffold.shipping_provider import ShippingProviderScaffold

	scaffold = get_current_app_scaffold(ShippingProviderScaffold, app)
	for change, path in scaffold.add_shipping_provider(label):
		click.echo(f"{change:<8} {path}")
	click.secho(
		"Next: implement get_rates, then bench --site <site> migrate. See docs/implementation/shipping-providers.md.",
		fg="green",
	)


def get_current_app_scaffold(scaffold_class=None, app=None):
	from frappe.utils import get_bench_path

	from commera.scaffold import AppScaffold, get_app_from_folder

	apps_path = Path(get_bench_path()) / "apps"
	# bench runs every command from sites/, so only $PWD still says which app folder the user is in.
	return (scaffold_class or AppScaffold)(
		app or get_app_from_folder(Path(os.environ.get("PWD") or os.getcwd()), apps_path), apps_path
	)


commands = [commera_commands]
