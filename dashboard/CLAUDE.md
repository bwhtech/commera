# Commera dashboard — house law

The admin SPA: Vite + Vue 3 (`<script setup>`, Composition API) + frappe-ui, served at
`/commera`. It talks to `commera.api.admin.*` and to nothing else.

**This file overrides the repo-root and global CLAUDE.md for everything under `dashboard/`.**
The global file's frontend doctrine ("Jinja + Tailwind + Alpine, no SPA frameworks") is written
for the storefront's portal pages. It does not apply here. What carries over unchanged: full
variable names, comments explain *why*, async/await only, no `{"success": true}` envelopes.

Reviewers: cite a rule below by its heading. A finding that cites nothing is an opinion.

## 1 — One door to the server

Every read and write goes through `data/api.js`:

| helper | use |
| --- | --- |
| `useAdminRead(path, options)` | GET an `commera.api.admin.*` method |
| `useAdminAction(path, options)` | POST one; `immediate: false`, fires on `.submit()` |
| `useMethodRead` / `useMethodAction` | full dotted path, for an endpoint shared with Desk |
| `createAdminCaller(modulePath)` | a module whose screen calls many of its methods |

**BLOCKING:** no `fetch`, no `frappe.call`, no bare `useCall`, `createResource`, or
`createListResource` in a component. The wrappers exist because the URL must be the absolute
`/api/v2/method/` path — v1 answers `{"message": ...}` and frappe-ui's `useCall` unwraps
`data.value?.data`, so a v1 call silently resolves to `null` on every screen. That failure is
invisible, which is why the rule is absolute.

`createAdminCaller` is one `useCall` per method by design: a single call over a mutable URL
aborts the in-flight request and hands every caller the same `data`.

## 2 — A failure is already handled

`useAdminRead` / `useAdminAction` toast the error. A screen must **not** toast it again.
Read the refusal off the request (`request.error`) when the screen has to tell a refusal from a
genuinely empty answer, or use `attempt()` from `createAdminCaller` to get both halves.
`errorMessage()` in `data/errors.js` is the only place that strips Frappe's `SomethingError:`
prefix and its `<strong>` markup — never re-implement that stripping.

## 3 — Settings panels save themselves

There is no Save button anywhere in Settings. A panel composes `useSettingsAutosave(save)` and
each control commits its own field when it **settles** — blur for a text box, change for a
select or check — never per keystroke.

- `adopt(record)` merges the server's truth in; it never replaces, because a panel adopts the
  fields it owns one answer at a time.
- `set(fieldname, value)` is what is being typed.
- `commit(fieldname, value, label, afterSave)` writes exactly the one changed field, and rolls
  the box back to `stored` on refusal.

Submitting a whole draft object, or adding a Save button to a settings panel, is a
**BLOCKING** regression. `SettingsFieldRows` → `SettingsFieldControl` renders a group from
docfield descriptors; a settings screen should not hand-build inputs a third time.

## 4 — Where a file goes

| directory | holds |
| --- | --- |
| `data/` | server truth: one module per domain, exporting the resources and the pure shapers over them |
| `ia/` | client-side app state — nav, the settings dialog, the search palette, `localStorage` prefs. Never fetches |
| `utils/` | framework-level helpers with no app knowledge (`useIsMobile`) |
| `components/` | shared across domains |
| `components/<domain>/` | used by one domain only |
| `pages/` | routed screens, one per route, lazy-imported in `router.js` |

A `data/` module that renders, or an `ia/` module that fetches, is in the wrong directory.

## 5 — Reuse before you build (the DRY law)

These exist. Using something else in their place is a finding:

`AppPageHeader` (every page's title row, breadcrumbs, mobile back) · `PageBody` (page gutters
and bottom padding — `full` / `wide` / `narrow` / `form`) · `ListPagination` · `EmptyState` ·
`StatusBadge` · `ResponsiveButton` · `BulkBar` · `Thumb` · `ReportHeader` + `ReportStats` (all
three analytics reports wear these; the sameness is the point) · `SettingsFieldRows` ·
`IntegrationCard` / `IntegrationConfig` · `money` / `shortDate` from `data/format.js`.

Order of preference, hardest first: **a frappe-ui component → an existing component here → a
new shared component → local markup.** Hand-rolling a Button, Dialog, Select, Autocomplete, or
list scaffold that frappe-ui already ships is blocking; the live index is
<https://ui.frappe.io/llms.txt> and lists come from `frappe-ui/list`.

Two clones of the same block is a coincidence; three is a component. Judge extraction by whether
the pieces share a *reason*, not by whether the lines match — `jscpd` measures the lines, and it
already reports this tree at ~1.4%, so the remaining duplication is semantic and needs a reader.

## 6 — Styling

Tokens only: `text-ink-gray-*`, `bg-surface-gray-*`, `border-outline-gray-*`, `text-ink-red-6`,
`rounded-4` / `rounded-5`, `text-lg-semibold` / `text-p-sm` and the rest of frappe-ui's scale.

**BLOCKING:** a hex or named colour, an arbitrary `text-[13px]`-style value where a token exists,
a `style="..."` attribute, or a class name built by string concatenation. Tailwind only sees
static class names — build variants with an object/array binding or a lookup map (see
`PageBody`'s `WIDTHS`).

A colour the store owner picked is exempt: it is data, not styling, and no class can hold an
arbitrary hex. Draw one through `SwatchDot`, which binds it with `:style`, rather than a new binding.

Icons are a `<span class="lucide-name size-4" aria-hidden="true" />`. There is no icon component.

Mobile-first, `sm` (640px) is the layout switch — `useIsMobile()` and `MobileLayout` both agree
on it. **`min-w-0` on a flex child is load-bearing**: frappe-ui's shells give children `flex-1`
with no min-width, so the `auto` floor holds the column at min-content width and the surplus is
clipped by an ancestor's `overflow-hidden`. Where you add it, say why.

## 7 — Comments

Why, never what — and this tree holds a high bar for it. A non-obvious layout hack, a magic
offset, a framework workaround, or an ordering that matters gets a comment explaining the
*mechanism* and what to recheck if it changes. Look at `AppPageHeader`'s `-ml-2` note or
`api.js`'s v2-path note for the standard. A comment that restates the code is a finding in the
other direction.

A deliberate shortcut gets `// ponytail: <ceiling>, <trigger to revisit>` — not a bare TODO.

## 8 — Style

2-space indent, single quotes, no semicolons, trailing commas — frappe-ui's own house style.
Identifiers are **camelCase**, components PascalCase. The global CLAUDE.md's `snake_case` is a
Python rule; it has never applied to JS and does not apply here. The only naming law that carries
over is *full words* — `productImport`, not `imp`.
There is **no biome or prettier config in this project**; a bare `npx biome check` reports ~200
findings against defaults this codebase does not follow. Do not treat it as a gate.
`components.d.ts` is generated by unplugin-vue-components — never hand-edit it, never review it.

## 9 — Verifying

```
npm run dev                # browse the site at <site>:8080, NOT the vite port
npm run build             # → ../commera/public/commera + ../commera/www/commera.html
npm run test:e2e          # needs a build first; check-build.js enforces it
```

The browser serves the **last build**, not your source. Rebuild before any e2e run, any
screenshot, and any claim that a change works. Both build outputs are gitignored.

UI changes are screenshot-driven: reference → current → name the exact diff → one change at a
time. Light and dark both, and the `sm` breakpoint both sides.

## 10 — `src/extension-api/` is a public API

Installed apps import it as `@commera/admin`, next to `vue`, `frappe-ui`, `frappe-ui/list` and `frappe-ui/charts`,
through the import map `vite.config.js` writes into `commera.html`. Renaming or removing an export, a prop of a
re-exported component, or a `useExtension()` member breaks every app built against it; add, never change. The build also
writes `commera/public/extension-host/` (shared export names, the class vocabulary and the icon list), which
the extension kit in `packages/extension-kit/` checks app builds against.

The dashboard draws every frame an app sits in: `ExtensionPageFrame` (header + body), `ExtensionCardFrame`,
`ExtensionActionDialog` and `ExtensionSettingsPanel`. Apps reach that chrome only through `usePage()`, `useCard()`
and `useAction()`, so never export `AppPageHeader`, `PageBody` or a card wrapper from `@commera/admin`.
