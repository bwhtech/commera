import subprocess
from pathlib import Path

import click


@click.group("commera")
def commera_commands():
	"""Commera tools for apps that extend the Commera dashboard."""


# After an app name bench runs its own command of the same name (init, setup, new-app...), so avoid those.
@commera_commands.command("scaffold")
@click.argument("app")
@click.option("--skip-install", is_flag=True, default=False, help="Do not run yarn install in the app")
def scaffold(app: str, skip_install: bool):
	"""Set up APP to add pages, cards, actions and settings to the Commera dashboard."""
	from frappe.utils import get_bench_path

	from commera.scaffold import AppScaffold

	scaffold = AppScaffold(app, Path(get_bench_path()) / "apps")
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
