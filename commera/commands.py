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

	click.secho(f"Next: bench build --app {app}, then open /commera", fg="green")


commands = [commera_commands]
