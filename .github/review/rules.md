# Commera review rules

The review bot cites these rules by their heading, for example "rules.md, Data access". A finding that breaks a rule here is must fix. A finding outside these rules is must fix only when it is a real defect that you can show with a concrete input.

## Data access

- New code does not use `frappe.db.sql`. Use `frappe.qb`, `frappe.get_all` or `frappe.db.get_value`.
- No `frappe.get_doc` or `frappe.get_cached_doc` inside a loop. Fetch the rows once with `frappe.get_all` and build a map.
- Request data is parsed with `frappe.parse_json`, never `json.loads`.
- Type conversion uses `cint`, `flt`, `cstr`, `getdate` and `get_datetime`. No new helper does the same job.

## Permissions

- `ignore_permissions=True` needs a reason that the reviewer can confirm in the code around it.
- A guest endpoint (`allow_guest=True`) validates its input and carries `@rate_limit`.
- A request that changes state is a POST. A GET never writes.
- A portal page that reads the session user's data sets `no_cache` before any early return.
- Shopper records are scoped with `owner == frappe.session.user` in the query. This is the house pattern. Do not ask for `has_permission` on top of it, and do not ask to widen it to staff: staff never place orders.

## Hooks and jobs

- `doc_events` in `hooks.py` point at a wrapper in `commera/doc_events/<doctype>.py`, never at a feature function.
- Heavy work in a request goes to `frappe.enqueue`.
- `frappe.enqueue` keeps `event`, `queue`, `timeout`, `job_name`, `now`, `at_front` and `enqueue_after_commit` for itself. A job argument with one of these names never reaches the job.
- Publish and enqueue calls that depend on a new document run after commit.

## Dashboard

- The dashboard follows `dashboard/CLAUDE.md`.
- A new dashboard dependency is in both `yarn.lock` and `package-lock.json`. CI installs with `npm ci`.
- A record is edited in the same panel with a Back button, never in a dialog opened from a dialog. Pickers and confirmations are fine.
- Links use weight, not colour. The dashboard has a neutral palette.

## Code

- Names are full words: `sales_order`, not `so`. Functions have no leading underscore.
- One verb per meaning: `get`, `set`, `add`, `save`, `remove`, `format`, `refresh`, `reset`.
- No `{"success": True}` envelopes. Return the data, and throw on error.
- A comment explains a reason the code cannot show. A comment that repeats the code is removed.
- Reuse before writing: a framework or codebase utility first, then one shared helper, then a new function.

## Tests

- A change in behaviour has a test through the real path, on a real database. Do not ask for tests of helpers or configuration.

## Pull request

- The title is a conventional commit: `type(scope): subject`. `chore` is wrong for a change that reaches production.
- `closes #N` is used only when the PR does everything the issue asks. Otherwise it is `refs #N`.
- A UI change has a screenshot in the description.

## Do not flag

- Style that Ruff, Biome or pre-commit already check.
- A defect older than the PR, on lines the PR does not touch. Put it under "Deferred". It is must fix only when the PR makes it worse or easier to reach.
- A problem that needs an input you cannot name.
