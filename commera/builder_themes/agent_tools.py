"""The tools Commera gives Bob, Builder's agent, on a theme page, through the builder_agent_tools hook."""

import json

import frappe

from commera.builder_themes.checks import Problem, check_page
from commera.builder_themes.pages import get_page_role

CHECK_PAGE = "commera_check_page"


def get_tools() -> list:
	# Builder is optional, and it calls this hook only when it is installed.
	from builder.ai.agent.registry import Tool

	return [
		Tool(
			name=CHECK_PAGE,
			side="server",
			description=(
				"Check a Commera theme page: every binding names a real key of the page's data, and the "
				"page has the parts a store page needs (cart link, add to cart, sizes, product cards, "
				"pagination). It lists each problem with its block and the fix. Call it before you finish "
				"a turn that changed a theme page."
			),
			parameters={
				"type": "object",
				"properties": {
					"page": {
						"type": "string",
						"description": (
							"The page id of another page of this theme, to check it with the edits you "
							"prepared for it. Leave out to check this page."
						),
					}
				},
			},
			handler=run_check_page,
			label=("Checking the page for the store", "Checked the page for the store"),
			available=is_theme_page,
		)
	]


def is_theme_page(ctx) -> bool:
	page = getattr(ctx, "page_id", None)
	return bool(page and get_page_role(page))


def run_check_page(ctx, args: dict) -> str:
	page, why = find_page(ctx, args.get("page"))
	if not page:
		return f"FAILED: {why}."
	# before the role: a page the user cannot read must not show whether it is a theme page
	if not frappe.has_permission("Builder Page", "read", doc=page):
		return f"FAILED: you cannot read page {page}."
	role = get_page_role(page)
	if not role:
		return f"FAILED: {page} is not a page of a Commera theme."
	return describe(role.page_type, check_page(role.page_type, get_root(ctx, page)))


def find_page(ctx, reference: str | None) -> tuple[str | None, str]:
	"""This turn's page, or the page Bob names by id, title, route or URL."""
	from builder.ai.agent.tools.query import resolve_page_reference

	reference = (reference or "").strip()
	return resolve_page_reference(reference) if reference else (ctx.page_id, "")


def get_root(ctx, page: str) -> dict | None:
	"""The page with this turn's edits: Bob checks what it built, not what was saved before."""
	from builder.ai.agent.tree import ComponentTree

	if page != ctx.page_id:
		# edits to another page wait for the user's OK, so Builder holds them apart from the page
		held = ctx.page_changes.tree_of(page) if getattr(ctx, "page_changes", None) else None
		return held.root if held else get_saved_root(page)
	tree = getattr(ctx, "tree", None)
	# while Bob edits a component, the tree holds that component, not the page
	if tree is None or isinstance(tree, ComponentTree):
		return get_saved_root(page)
	return tree.root


def get_saved_root(page: str) -> dict | None:
	draft, published = frappe.db.get_value("Builder Page", page, ["draft_blocks", "blocks"])
	blocks = json.loads(draft or published or "[]")
	return blocks[0] if blocks else None


def describe(page_type: str, problems: list[Problem]) -> str:
	"""The reply Bob reads: FAILED while a problem is open, so it fixes them before it answers the user."""
	if not problems:
		return f"OK: the {page_type} page passes Commera's checks."
	failures = [problem for problem in problems if not problem.is_warning]
	warnings = [problem for problem in problems if problem.is_warning]
	lines = []
	if failures:
		lines.append(f"FAILED: {len(failures)} to fix on the {page_type} page, then check again.")
		lines.extend(describe_problem(problem) for problem in failures)
	else:
		lines.append(f"OK: the {page_type} page has no problems.")
	if warnings:
		lines.append("Warnings (fix them unless the design leaves the part out on purpose):")
		lines.extend(describe_problem(problem) for problem in warnings)
	return "\n".join(lines)


def describe_problem(problem: Problem) -> str:
	if not problem.block:
		return f"- {problem.message}"
	where = f"block {problem.block}"
	if problem.component:
		where += f" of component {problem.component}"
	return f"- {where}: {problem.message}"
