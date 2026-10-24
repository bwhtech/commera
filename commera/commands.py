import json
import os
from pathlib import Path

import click
import frappe


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


@commera_commands.group(
	"theme", help="Build storefront themes from files: scaffold a theme and lint it. No site needed."
)
def theme_commands():
	pass


@theme_commands.command(
	"check", help="Lint a theme's sections, layouts and settings. Exits 1 when there are errors."
)
@click.option("--theme", "theme_slug", help="Slug of the theme to check; every theme when left out")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print only the findings, as JSON")
def check(theme_slug: str | None, as_json: bool):
	frappe.init("")
	from commera.shop_themes.theme_check import check_themes_on_disk, count_errors, format_findings

	findings = check_themes_on_disk(theme_slug)
	click.echo(json.dumps(findings, indent=1) if as_json else format_findings(findings, not theme_slug))
	click.get_current_context().exit(1 if count_errors(findings) else 0)


@theme_commands.command(
	"new", help="Scaffold a theme folder and its Shop Theme record, which bench migrate imports."
)
@click.option("--app", required=True, help="App the theme ships in")
@click.option("--slug", required=True, help="Folder name of the theme, in snake_case")
@click.option("--parent", default="shop_base_theme", show_default=True, help="Slug of the theme to inherit")
@click.option("--name", "theme_name", help="Shop Theme name; defaults to the slug in title case")
@click.option("--module", help="Module of the Shop Theme record; defaults to the app's first module")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print only the result, as JSON")
def new(app: str, slug: str, parent: str, theme_name: str | None, module: str | None, as_json: bool):
	frappe.init("")
	from commera.shop_themes.theme_scaffold import create_theme

	result = create_theme(None, app, slug, parent, theme_name, module)
	if as_json:
		click.echo(json.dumps(result, indent=1))
		return
	click.echo(f"Created {app}/themes/{slug}/")
	for path in result["created"]:
		click.echo(f"  {path}")
	click.secho(f'The Shop Theme "{result["theme"]}" is created on the next bench migrate.', fg="green")


@theme_commands.command("new-section", help="Write sections/<type>.html and .json in a theme.")
@click.option("--theme", "theme_slug", required=True, help="Slug of the theme to add the section to")
@click.option("--type", "section_type", required=True, help="Section type in snake_case, e.g. testimonials")
@click.option("--blocks", default="", help="Comma-separated block types, e.g. quote,rating")
@click.option(
	"--group", type=click.Choice(["header", "footer"]), help="Place it in the shared header or footer"
)
@click.option("--templates", default="", help="Comma-separated page types it may be placed on, e.g. product")
@click.option("--static", is_flag=True, default=False, help="Reorderable, not removable")
@click.option("--controller", is_flag=True, default=False, help="Also write <type>.py with get_context")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print only the result, as JSON")
def new_section(
	theme_slug: str,
	section_type: str,
	blocks: str,
	group: str | None,
	templates: str,
	static: bool,
	controller: bool,
	as_json: bool,
):
	frappe.init("")
	from commera.shop_themes.section_scaffold import create_section

	result = create_section(
		theme_slug, section_type, split_list(blocks), group, split_list(templates), static, controller
	)
	click.echo(json.dumps(result, indent=1) if as_json else format_changed_files(result, "Wrote"))


@theme_commands.command(
	"new-block", help="Add a block type to a section's .json and its macro to the section's .html."
)
@click.option("--theme", "theme_slug", required=True, help="Slug of the theme")
@click.option("--section", "section_type", required=True, help="Section type the block belongs to")
@click.option("--type", "block_type", required=True, help="Block type in snake_case, e.g. rating")
@click.option("--static", is_flag=True, default=False, help="Placed with render_static_block, not movable")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print only the result, as JSON")
def new_block(theme_slug: str, section_type: str, block_type: str, static: bool, as_json: bool):
	frappe.init("")
	from commera.shop_themes.section_scaffold import create_block

	result = create_block(theme_slug, section_type, block_type, static)
	click.echo(json.dumps(result, indent=1) if as_json else format_changed_files(result, "Updated"))
	if static and not as_json:
		click.echo(
			f'Place it in sections/{section_type}.html with {{{{ render_static_block("{block_type}") }}}}'
		)


def split_list(value: str) -> list[str]:
	return [item.strip() for item in value.split(",") if item.strip()]


def format_changed_files(result: dict, verb: str) -> str:
	return "\n".join(f"{verb} {path}" for path in result.get("created") or result.get("changed"))


def get_current_app_scaffold():
	from frappe.utils import get_bench_path

	from commera.scaffold import AppScaffold, get_app_from_folder

	apps_path = Path(get_bench_path()) / "apps"
	# bench runs every command from sites/, so only $PWD still says which app folder the user is in.
	return AppScaffold(get_app_from_folder(Path(os.environ.get("PWD") or os.getcwd()), apps_path), apps_path)


commands = [commera_commands]
