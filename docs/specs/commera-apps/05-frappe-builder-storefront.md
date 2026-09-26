# Commera Apps — Frappe Builder as a storefront source (research)

Spec 5. Research note, not a build plan yet. It answers three questions: what Frappe Builder's
extension work (in flight, September 2026) gives us, how a merchant could build storefront pages in
Builder instead of a Jinja theme, and how Commera can hand storefront context to Builder's AI agent,
Bob. It ends with the asks for the Builder maintainers, who have said they are open to shaping
extensions around this.

Status: research, 2026-09-26. Based on `frappe/builder` `develop` plus open PRs #875, #876 and #877.

## Summary

- Builder's extension API (#875) is a **front-end, sandboxed-iframe, per-editor** system. An
  extension is a built `main.js` and a manifest, installed from Builder Hub, and it talks to the
  editor over a `MessagePort`. It has **no server-side extension point, no data-source concept and no
  AI hook**. Nothing in it lets an installed Frappe app (like Commera) add context to pages or to
  Bob.
- Bob (`builder/ai/`) builds its tool list and system prompt from hard-coded lists. `AgentRunner`
  already accepts `registry=` and `system_prompt=`, but nothing passes them, and Builder never calls
  `frappe.get_hooks`. **Today no app can add tools or context to Bob without monkeypatching.**
- Builder page data scripts run in a sandbox. On a site without server scripts enabled (the common
  case, Frappe Cloud included) that sandbox is Builder's `safer_exec`, which has **no `frappe.call`**.
  So a page data script cannot reach Commera code: no cart, no priced variants, no stock.
- The rollout for #875 is six parts. Only parts 1 and 2 have PRs (#876, #877). **Part 3, which the
  author says "carries the main design review" (the SDK protocol), has not started.** That makes now
  the right time to ask for app-level hooks.
- Recommendation: add a "storefront source" switch (Commera theme or Frappe Builder), with Builder
  covering the content-heavy templates (home, collection, product, content pages). Cart, checkout and
  account stay Commera-rendered. Ask upstream for three server hooks: **data providers**,
  **AI context** and **AI tools**, plus **app-shipped extensions**. Everything else we can build on
  our side.

## 1. What Builder is building

### PR map

| PR | State | What it is |
|---|---|---|
| [#875](https://github.com/frappe/builder/pull/875) "add an extension API" | open, draft | The whole reference implementation (215 files). It will not merge as-is; it is split into six parts. |
| [#876](https://github.com/frappe/builder/pull/876) "lock built-in registry items" | open | Part 1. `registerBuiltIn` / `unregisterBuiltIn`: extensions cannot replace or remove Builder's own toolbar, panel and settings items. Also small fixes. |
| [#877](https://github.com/frappe/builder/pull/877) "server access model for extensions" | open | Part 2. DocTypes `Builder User Extension` and `Builder Extension State`, and `assert_extension_access`. During review, installs became **site-wide** and managed by an "Extension Manager Role"; per-doctype grants were dropped in favour of Frappe's own permissions. |
| parts 3–6 | not started | 3: SDK protocol, frame host, dev loader, toolbar. 4: more surfaces plus block/page/token/state methods. 5: schema access, grant dialog. 6: Hub install, Extensions panel, packager, templates. |
| [#751](https://github.com/frappe/builder/pull/751) "site-aware Bob" | merged | On-demand orientation (Bob reads the site with tools rather than getting a pre-built summary), reference-page reads, web research. |
| [#824](https://github.com/frappe/builder/pull/824) | closed | "Revert every document an AI turn changed and tell Bob about manual edits." |

### The extension model in #875

- **Package:** `manifest.json` (`v: 1`, `name: "publisher/name"`, `label`, `description`, `version`,
  `entry: "main.js"`, `icon`, `capabilities`) plus `main.js`. Unknown manifest fields are rejected.
  It is released as a `.builderext` on a GitHub release and installed from Builder Hub. Developer
  mode can load one extension from a Vite dev server.
- **Runtime:** every extension runs in `sandbox="allow-scripts allow-forms"` iframes at an opaque
  origin. There is one hidden `main` frame, plus `panel`, `settings`, `dialog` and `popover` frames
  opened on demand. The SDK (`frappe-builder-extension-sdk`) is served by Builder and loaded through
  an import map. This is the same shared-runtime approach as our `poc/extension-runtime`.
- **Surfaces:** toolbar buttons, context-menu rows, property sections (host-rendered `text`,
  `number`, `select`, `toggle`, `color`, `range` controls bound to a block attribute or style), one
  left-panel tab, one settings page, a dialog, a popover, and an "Open" button.
- **Capabilities:** `context.read`, `block.read`, `block.update`, `block.insert`, `page.read`,
  `page.write` (attach one JS and one CSS client script per page), `token.write`, `ui.dialog`,
  `ui.popover`, `data.access` (`getList`/`getDoc`/`insert`/`update`/`delete` as the session user), and
  `schema.write` (create DocTypes).
- **Server:** `builder/extensions/*.py` covers access, installation, Hub download and verification,
  extension-owned client scripts and tokens (`Builder Extension Resource`), and state.

### What it does not cover, and what we need

| We need | #875 gives | Gap |
|---|---|---|
| Commera, an installed Frappe app, contributes to Builder | Hub-installed JS packages | No way for a Frappe app to ship an extension with the app. Hub, GitHub releases and a review queue are the only route. |
| Storefront data (product, price, stock, cart) on a published page | Nothing at render time; `data.access` works in the editor only | No server-side data provider. The page data script sandbox cannot call app code. |
| The editor knows which data keys a page has (for binding UI and for Bob) | `context.get()` is selection/page/site only | No data schema. |
| Bob knows about the store and can act on it | Nothing | No AI hook of any kind. |
| Commera blocks (add-to-cart, variant picker, price) that work on the published page | `block.insert` and `page.attachScript` | Workable (see §3), but no notion of an app-owned block type. |

## 2. How Bob works today

Code is in `builder/ai/`.

- **Entry point:** `api.run(prompt, page_id, …)` enqueues `run_agent_job`, which runs
  `agent/loop.py: AgentRunner`. Models go through LiteLLM (`llm.py`). There is also a Codex/ChatGPT
  OAuth path.
- **Prompt:** one static `Prompts.AGENT_SYSTEM` (`prompts.py`). `build_messages()` then adds a
  synthetic context turn containing:
  - the open page (title, route, state);
  - the page's block tree as compact YAML, plus component contracts;
  - every `Builder AI Memory` row.

  Nothing else is pre-loaded. By design, Bob "orients" himself with read tools (prompts.py:87).
- **Tools** (`agent/registry.py: build_default_registry`, a hard-coded list):
  - generating and editing blocks, reading pages;
  - scripts, settings and tokens, components;
  - data: `list_doctypes`, `get_doctype_schema`, `query_records`, `get_document`,
    `write_page_data_script`, `create_doctype`, `seed_sample_data`;
  - `run_python` (a read-only sandbox);
  - `remember`, `research` / `read_url`, images, preview.

  A tool is a dataclass: `Tool(name, side, description, parameters, handler(ctx, args) -> str)`.
  `side="server"` tools only need a handler, so they are cheap to add from outside. Client tools also
  need `agent/tree.py` and the front-end `ToolDispatcher`, so they are not.
- **Data awareness:** Bob does not see a page's data script or its keys up front. He must
  `get_document('Builder Page', …)` or run Python. For a Commera page he would guess at `Item` and
  `Website Item` rows and miss Commera's pricing, variant, stock and cart logic entirely.
- **What works without upstream changes:**
  - **`Builder AI Memory` rows:** up to 50, 500 characters each, and every row is sent on every turn.
    Commera could insert a few facts ("this site is a Commera store; product pages use …"). They share
    space with user memories, and Bob can forget them.
  - **Monkeypatching** `build_default_registry` and `Prompts.AGENT_SYSTEM`. Fragile; don't.

## 3. Builder as a storefront source (Commera side)

### Model

Add a `storefront_source` select to **Shop Theme Settings**: `Theme` (today) or `Frappe Builder`.
With `Frappe Builder`, a new child table, **Shop Builder Page Map**, maps each template to a Builder
Page:

| Template | Builder page | Route rule |
|---|---|---|
| `index` | static page | `^/(en\|ar)?$` |
| `collection` | dynamic page, `products` or `category/<category>` | listing filters stay query params |
| `product` | dynamic page, `products/<route>` | |
| `page` | any number of free-form pages | Builder owns their routes |

Cart, checkout, account and order pages stay theme-rendered, as spec 4's non-goals already say. The
active theme also supplies the chrome for those pages, so a Builder store still sets a theme. (Its
header and footer can later be Builder components too; see open questions.)

The merchant picks pages from Builder in the Commera dashboard. "Edit in Builder" deep-links to
`/builder/page/<name>`.

### Rendering and context

Commera's `ThemePageRenderer` already runs first for storefront routes. For a mapped template it
would:

1. build the same context the theme controller builds today (`www/products/details.py`, etc.);
2. hand that context to the mapped `Builder Page`'s render, so block bindings like `product.title`
   and `selected_price` resolve.

`BuilderPage.get_context` merges the page data script's output and then renders the blocks as Jinja
with the whole context (builder_page.py:545–599). So keys Commera puts in the context are visible to
bindings, *if* they are there before that render. Whether we can do this without subclassing
Builder's renderer is the first spike. It is also why a proper **data provider hook** (asks, §5) is
the clean version.

### Commerce behaviour on a Builder page

A Builder page is static HTML plus Jinja. Interactive commerce (variant switch, add to cart, cart
drawer) comes from:

- **Commera components shipped in Commera**, synced through Builder's standard `builder_files` sync
  (`<app>/builder_files/components/…`, run on `after_migrate` for every app): product gallery,
  price, variant picker, add-to-cart button, product grid, cart icon. Each one is bound to the context
  keys above, with markup that carries `data-commera-*` attributes.
- **One Commera storefront script**, loaded on mapped pages, that wires those attributes to the same
  `commera:cart:*` / `commera:variant:changed` events spec 4 defines. Theme and Builder pages then
  share one cart implementation.
- **Spec 4 app blocks:** `storefront_block(...)` in Builder is the same idea as the components above.
  The open question in spec 4 ("can Builder reuse section schemas as Builder blocks?") becomes:
  generate one Builder component per app block, with settings mapped to component props.

### A Commera Builder extension (optional, after part 4 ships)

A small extension adds a "Commerce" left-panel tab (insert product grid, bind block to product
field, pick a collection) and property sections for Commera components. This is UX sugar and needs
the "app-shipped extension" ask below. The rendering path above works without it.

## 4. Context for Bob

Goal: when a merchant says "make a product page that shows the size chart and a sticky add to cart",
Bob knows:

- this is a Commera store;
- which template the page is mapped to and which keys it gets;
- which Commera components exist;
- that cart and checkout are off-limits;
- the merchant's catalogue (categories, collections, a sample product);
- the rules ("prices always come from `selected_price`, never hard-code").

Three kinds of contribution, cheapest first:

1. **Static guidance.** A short prompt fragment plus a longer reference document fetched on demand.
   This matches Bob's "orient yourself" design: a tool `get_app_guide("commera")` rather than 5k
   tokens on every turn.
2. **Dynamic per-page context.** `fn(page, user) -> str | None`, called in `build_messages()`. For a
   page mapped to `product` it returns the keys available, a sample product's values, and the Commera
   components the page may use. It returns `None` on pages Commera does not own.
3. **Tools.** Read-only server tools with Commera's own logic:
   - `commera_list_collections`;
   - `commera_sample_product(route?)`, which returns the exact context dict a product page gets;
   - `commera_storefront_map`, which lists which Builder page serves which template.

   Every tool runs as the session user and follows the same rules as Bob's `READ_ONLY_SERVER_TOOLS`.

Every piece lives in Commera's Python, next to the controllers that produce the context, so it
cannot drift from what the page really renders.

## 5. Asks for the Builder maintainers

Ordered by value to us. Each ask is small on Builder's side and useful to any app, not only Commera.

1. **AI context hook.** Suggested name: `builder_ai_context`. A list of dotted paths, each called as
   `fn(page: str | None, user: str) -> str | None`. Builder appends the non-empty results to the
   context turn in `AgentRunner.build_messages()`, each under a heading naming its app, with a size
   cap per app.
2. **AI tools hook.** Suggested name: `builder_ai_tools`. A list of dotted paths returning `Tool`
   definitions, limited to `side="server"` and read-only by default. `build_default_registry()`
   extends with them; `READ_ONLY_SERVER_TOOLS` honours a `read_only=True` flag. Tool names are
   namespaced by app (`commera.sample_product`).
3. **Page data providers.** Suggested name: `builder_data_providers`. A provider looks like:
   `{"name": "commera.product", "label": "Product", "routes": ["products/<route>"],
   "schema": fn() -> keys and types, "get_data": fn(route_params) -> dict, "sample": fn() -> dict}`.
   - A page picks a provider in page settings. Builder merges `get_data()` before the page data
     script runs, so the script can still add to it.
   - `schema()` feeds the binding picker and Bob's context.
   - `sample()` feeds editor preview (`get_page_data`).

   This also fixes the `safer_exec` problem without widening the sandbox.
4. **App-shipped extensions.** An installed Frappe app declares
   `builder_extensions = ["commera/builder_extension"]`, pointing at a built `main.js` and
   `manifest.json` inside the app. Builder installs it site-wide on `after_app_install` / migrate and
   removes it on uninstall. This fits #877's move to site-wide installs. The app is already trusted
   code on the server, so no Hub review is needed.
5. **Manifest room for AI.** If extensions stay front-end only, allow an `ai` block in the manifest
   (a guide path, and a list of the extension's actions exposed as tools). Bob could then call an
   extension's action through the host. This is lower priority than 1–2, because Bob runs in a
   background job, not in the editor.
6. **Stable component contracts for app components.** The props plus data-key contract Bob already
   reads (`build_page_context`), marked `app: commera` and protected from edits the way built-in
   registry items are in #876.

Two things to confirm with them:

- **Renderer precedence:** Commera's `page_renderer` and Builder's `resolve_path` /
  `BuilderPageRenderer` both claim routes. Which one wins for `products/<route>`?
- **Security findings on #877:**
  - `data.access` is now unbounded within the user's permissions. For a store admin that includes
    customers and orders, so for us it should be narrowed, or at least shown clearly at install.
  - Website Managers can reassign `extension_manager_role`.

## 6. Phasing

| Phase | Needs upstream | Scope |
|---|---|---|
| B0 spike | no | Render a mapped `product` Builder page through `ThemePageRenderer` with Commera context. Prove bindings, `no_cache` and SEO. Decide subclass vs render-with-context. |
| B1 | no | `storefront_source` switch, page map, Commera components via `builder_files`, the shared storefront script, and the dashboard page picker. |
| B2 | asks 1–2 | Commera AI guide, per-page context, read-only tools. |
| B3 | ask 3 | Move context injection from the renderer to a data provider; binding picker shows Commera keys. |
| B4 | ask 4 + #875 part 4 | "Commerce" Builder extension (panel and property sections). |

## Open questions

- Header and footer on Builder pages: a Builder component per theme, or a Commera-rendered include?
  This affects whether cart, checkout and account look like the rest of the site.
- Arabic and RTL: Builder has page `language`. Do we map one Builder page per language, or bind
  translatable text from Commera context?
- Caching: Builder sets `no_cache` for dynamic pages. Product pages today rely on Commera's own cache
  rules (`website_context.py`). Which layer owns this?
- Should theme sections (spec 4) and Builder components share one schema source, so that a section
  written once works in both?
