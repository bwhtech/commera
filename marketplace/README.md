# Commera marketplace

The list of apps built for Commera. It uses the same format as
[frappe/marketplace](https://github.com/frappe/marketplace), so the same tools can read it.

- `apps.json` has one entry per app: `name`, `title`, `description`, `repo`, `category` and `releases`.
- `apps/<name>.json` lists that app's releases. Each release pins one commit on a branch, with the
  `frappe_core` range and `dependencies` taken from the app's `pyproject.toml` at that commit.

To list an app, add its entry to `apps.json`, add `apps/<name>.json` with at least one release, and
open a pull request.
