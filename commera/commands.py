import os
import subprocess
from pathlib import Path

import click


@click.group("commera")
def commera_commands():
	"""Commera tools for plugins that extend the Commera dashboard."""


# Run from the bench folder, bench skips the app name "commera" and runs its own `bench init` instead.
@commera_commands.command("init")
@click.option("--skip-install", is_flag=True, default=False, help="Do not run yarn install in the app")
def init(skip_install: bool):
	"""Set up the app you are in as a Commera plugin that adds pages, cards, actions and settings to the Commera dashboard."""
	from frappe.utils import get_bench_path

	from commera.scaffold import AppScaffold, get_app_from_folder

	apps_path = Path(get_bench_path()) / "apps"
	# bench runs every command from sites/, so only $PWD still says which app folder the user is in.
	app = get_app_from_folder(Path(os.environ.get("PWD") or os.getcwd()), apps_path)
	scaffold = AppScaffold(app, apps_path)
	for change, path in scaffold.save():
		click.echo(f"{change:<8} {path}")

	if not skip_install:
		click.echo("Running yarn install…")
		try:
			subprocess.run(["yarn", "install"], cwd=scaffold.app_root, check=True)
		except (FileNotFoundError, subprocess.CalledProcessError) as error:
			raise click.ClickException(f"yarn install failed in {scaffold.app_root}: {error}")

	click.secho("Next: run yarn dev in apps/commera/dashboard, then open /commera on port 8080", fg="green")
	click.echo(f"For production: bench build --app {app}")


@commera_commands.command("add")
@click.argument("kind")
@click.argument("name", required=False)
@click.option(
	"--detail", is_flag=True, default=False, help="With a page, also add [...id].vue for one record's view"
)
def add(kind: str, name: str | None, detail: bool):
	"""Add one starter placement to the plugin you are in: page, order-card, product-card, customer-card,
	order-action, product-action, customer-action, settings or command."""
	from frappe.utils import get_bench_path

	from commera.scaffold import AppScaffold, get_app_from_folder

	apps_path = Path(get_bench_path()) / "apps"
	app = get_app_from_folder(Path(os.environ.get("PWD") or os.getcwd()), apps_path)
	for change, path in AppScaffold(app, apps_path).add_place(kind, name, detail):
		click.echo(f"{change:<8} {path}")
	click.secho(
		"A running yarn dev in apps/commera/dashboard picks it up; otherwise run bench build --app " + app,
		fg="green",
	)


commands = [commera_commands]
