# Commera Apps — Agent-ready themes and apps

Spec 7 of 7. How Commera makes its developer APIs usable by coding agents (Claude Code, Codex, Cursor
and others), so that a developer can describe a theme and let an agent build it with little hand-holding.
It adds three things:

- the **storefront data API** that themes use (the refactor that specs 4 and 6 assume);
- **machine-readable tooling** that an agent can call and read;
- an **agent skill** that Commera ships.

The APIs themselves are defined in [spec 1](01-developer-api.md) (apps) and
[spec 4](04-theme-sections-and-layouts.md) (themes). This spec does not repeat them; it makes them
usable by an agent. The draft skill is in [`agent-skills/commera-theme/SKILL.md`](agent-skills/commera-theme/SKILL.md).

Status: draft.

## Why

Most new themes and apps will be started by a developer prompting an agent. An agent does well when:

- the APIs are **small, typed and documented next to the code**;
- the right structure comes from a **generator**, not from memory;
- mistakes produce **errors with rule ids and fixes**, not a blank page;
- it can **see the result** by rendering and screenshotting without a browser session;
- it has **one guide** that tells it the workflow and the rules.

Today a Commera theme has none of these. Templates call `frappe.get_all` inline, page context keys
differ per controller and live only in the code, and nothing checks a theme except its own tests.
Specs 4 and 6 already fix the structure: sections, schemas, layouts and a CLI. This spec finishes the
job for data, verification and guidance.

## Goals

- A developer writes a short **brief**: store type, brand, pages, languages. An agent then produces
  a theme that passes `theme check` and the theme test suite, renders every template in English and
  Arabic on desktop and mobile, and needs only design review.
- The agent never has to read Commera's source to know what data exists. Every key it can use is
  listed by a command, typed and illustrated with sample values from the site.
- Guidance cannot drift from the code. The reference material an agent reads is generated from the
  SDK and schemas at the installed version.

## Non-goals (v1)

- A Commera-hosted agent. Builder themes get AI through Bob (spec 5, spec 6 §3.4); this spec is for
  code themes and apps built in a developer's own editor.
- An MCP server. The CLI with `--json` covers the same ground; an MCP wrapper is an open question.

## 1. Storefront data API (`commera.sdk.storefront`)

Themes get data from **one typed page context** and **one query module**, never from DocTypes. This is
the refactor: storefront controllers (`www/index.py`, `www/products/…`, `www/cart`, `shop_web_page`)
build these objects instead of each assembling its own dict, and every template and section receives
the same shapes.

### 1.1 Page context

Every template, section and block receives these globals:

| Name | Type | Present on |
| --- | --- | --- |
| `store` | `Store`: `name`, `logo`, `currency`, `languages`, `default_language`, `url` | every page |
| `request` | `Request`: `language`, `dir` (`ltr`/`rtl`), `path`, `customer` (or `None`) | every page |
| `menus` | `dict[str, Menu]` by handle (`main`, `footer`); `Menu.items[]` with `title`, `url`, `children` | every page |
| `theme` | the theme's `settings.json` values, resolved | every page |
| `template` | `"index"`, `"product"`, `"collection"`, `"page"`, `"cart"`, `"search"`, `"account"` | every page |
| `product` | `Product` | `product` |
| `collection` | `Collection` with `products: Paginated[ProductCard]` and `filters[]` | `collection` |
| `page` | `ContentPage`: `title`, `content_html` (in the request language), `seo` | `page` |
| `cart` | `Cart`: `items[]`, `subtotal`, `count` | every page (`count` only), full on `cart` |
| `search` | `SearchResults`: `query`, `results: Paginated[ProductCard]` | `search` |

The core types:

```python
# commera/sdk/storefront/types.py (dataclasses; JSON Schema generated from them)
class Money:        amount: Decimal; currency: str; formatted: str       # "SAR 120.00", locale-aware
class Image:        url: str; alt: str; width: int; height: int          # use |image_url(width=…) to resize
class ProductCard:  handle: str; url: str; title: str; image: Image | None
                    price: Money; compare_at_price: Money | None; available: bool; badges: list[str]
class Variant:      id: str; title: str; options: dict[str, str]; price: Money
                    compare_at_price: Money | None; available: bool; image: Image | None
class Product(ProductCard):
                    description_html: str; images: list[Image]; options: list[Option]
                    variants: list[Variant]; selected_variant: Variant; collections: list[CollectionRef]
                    made_to_order: bool; app_data: dict[str, dict]        # per app, from spec 1 apps
class Collection:   handle: str; url: str; title: str; description_html: str; image: Image | None
```

Rules the API enforces, and the skill repeats:

- **Prices are always `Money`**, formatted by Commera for the store's currency and the request
  language. Templates print `{{ product.price.formatted }}` and never format numbers themselves.
- **Text is already translated.** Product, collection and page fields come in the request language
  with English fallback, and translatable section settings do too (spec 4 §2.3).
- **Availability is decided by Commera**, including made-to-order items (spec 1 §3.2). Templates read
  `available`; they never check stock.

### 1.2 Queries for section controllers

A section that needs more than the page context loads it in `sections/<type>.py` through one module:

```python
from commera.sdk import storefront

def get_context(section, page):
    return {
        "products": storefront.products(collection=section.settings.collection,
                                        limit=section.settings.count, sort="best_selling"),
    }
```

| Function | Returns |
| --- | --- |
| `products(collection=None, handles=None, tag=None, sort="featured", limit=12)` | `list[ProductCard]` |
| `product(handle)` | `Product` or `None` |
| `collections(handles=None, limit=None)` | `list[Collection]` without products |
| `collection(handle, page=1, per_page=24, filters=None)` | `Collection` |
| `recommendations(product, limit=4)` | `list[ProductCard]` (related products) |
| `search(query, limit=12)` | `list[ProductCard]` |
| `menu(handle)` | `Menu` |

All results are published-only, priced for the current customer and cached per request. Setting types
`collection` and `product` (spec 4 §2.2) store handles, so a setting value can be passed directly.
`theme check` flags `frappe.*` calls in templates and controllers as errors in themes (warnings for
Commera's own, until migrated).

### 1.3 Jinja filters and helpers

| Helper | Does |
| --- | --- |
| `render_layout`, `render_block`, `render_static_block` | spec 4 §2.3–2.4 |
| `image_url(image, width=, height=, crop=)` | Resized, cached image URL |
| `asset_url(path)` | Theme asset with cache-busting, following the parent chain |
| `t("key")` | Translates a theme string from `locales/<lang>.json` |
| `money(value)` | Formats a raw number in the store currency (rarely needed; `Money` is formatted) |
| `url_for("product", handle)` | Canonical, language-prefixed URL |

### 1.4 Storefront JavaScript (`window.commera`)

Commera, not the theme, provides cart and variant behaviour in the browser, so every theme and app
block uses one implementation. Themes build the UI and bind it to this API:

```js
await commera.cart.add({ variant: 'TS-BLK-M', qty: 1 })   // resolves to the Cart; emits commera:cart:updated
await commera.cart.update(lineId, qty)
await commera.cart.remove(lineId)
commera.cart.get()                                         // current Cart, no request
commera.product.select({ Size: 'M', Colour: 'Black' })     // on product pages; emits commera:variant:changed
commera.format.money(amount)
```

- The events in spec 4 §4.1 are emitted by this module, so a theme implements them just by using it.
- Types ship as `commera-storefront.d.ts`. `bench commera theme new` references it, so editors and
  agents get completion.
- Themes may use Alpine (as today) or plain JS. The skill recommends Alpine stores that wrap
  `commera.cart` so that markup stays declarative.

## 2. Tooling an agent can drive

Every theme command from spec 4 §2.5 gains `--json`. Five more commands close the loop:

| Command | Output | Why an agent needs it |
| --- | --- | --- |
| `bench --site X commera theme context --template product [--handle H] [--json]` | The full page context for a real product on the site, as JSON | It learns exact keys and realistic values without reading source. |
| `bench commera theme describe --theme S --json` | Every section, block, setting, template, static part and accepted app block, with the layouts | One read shows the whole theme. It is used before editing an existing theme. |
| `bench commera theme check --json` | `[{rule, severity, file, line, message, fix}]` | Stable rule ids (`blocks-not-looped`, `query-in-template`, `untranslated-string`, …) and a concrete fix per finding. |
| `bench --site X commera theme render --theme S --template T [--handle H] [--lang ar] [--width 390] --out file.png\|.html` | A screenshot (headless Chromium) or HTML of the draft theme, without publishing it | The agent sees what it built and compares English and Arabic, desktop and mobile. |
| `bench --site X commera demo-data --preset fashion\|electronics\|grocery` | Sample products, collections, pages and menus, with images | A fresh dev site has something to render. Presets are chosen from the brief. |

Two more properties make the tooling safe for an agent to use unattended:

- **Deterministic and quiet.** Commands never prompt. With `--json`, stdout carries only JSON and
  exit codes are meaningful (0 clean, 1 findings, 2 usage error).
- **File-only writes.** The theme commands write only inside the theme folder. No command writes
  merchant data (Theme Layout rows) except `demo-data` on a site flagged as a developer site.

## 3. The skill

### 3.1 What it is

A skill is a folder with a `SKILL.md` (a short description that tells the agent when to load it, and
then the instructions) plus reference files the agent reads on demand. The format is shared by
Claude Code's skills, and an `AGENTS.md` pointer covers agents that don't load skills.

Commera ships two skills:

| Skill | Loaded when | Covers |
| --- | --- | --- |
| `commera-theme` | building or changing a Commera theme, section, block or storefront page | this spec's §1 and §2, spec 4, spec 6 content pages |
| `commera-app` | building an app that extends the dashboard, checkout or storefront | spec 1 (registry, builders, `@commera/admin`, `commera.sdk`), spec 2's rules, spec 4 §4 app blocks |

The draft of the first is in [`agent-skills/commera-theme/SKILL.md`](agent-skills/commera-theme/SKILL.md).

### 3.2 The hands-off workflow it teaches

The developer decides; the agent executes. The skill has the agent:

1. **Capture a brief.** If the developer has not given one, the agent asks once. Then it writes
   `themes/<slug>/BRIEF.md` with the store type, brand (colours, fonts, tone), languages, pages and
   their sections, reference sites, and must-haves. After this step it does not ask again unless a
   check cannot be satisfied.
2. **Plan sections from the brief.** It maps every page to sections and blocks, reusing the parent
   theme's sections where they fit (`theme describe`), and writes the plan into `BRIEF.md`.
3. **Scaffold** with `theme new`, `new-section` and `new-block`. It never hand-writes schema
   boilerplate.
4. **Implement** templates, CSS and controllers against §1. It learns data from `theme context`, not
   from Commera's source.
5. **Verify.** It runs `theme check --json` until clean, then `theme render` for every template in
   `en`/`ar` at 1280 and 390 wide, and looks at the screenshots. It fixes what it sees and repeats.
6. **Ship the defaults.** It writes `layouts/*.json` so that the brief's pages appear out of the box,
   and runs the theme test suite (`assert_theme_valid`, required events).
7. **Report.** Screenshots, the check summary, and a list of decisions a human should review.

### 3.3 Rules in the skill

These are short, testable statements, and most are enforced by `theme check`:

- **Data.** Data comes only from the page context and `commera.sdk.storefront`. No `frappe.*` calls
  and no DocType names in a theme.
- **Money, availability and translation** come from Commera (§1.1). Never format prices, check stock,
  or hard-code English in templates; use `t()` and translatable settings.
- **RTL.** Arabic is right-to-left. Use CSS logical properties (`margin-inline-start`, not
  `margin-left`), and `request.dir` on `<html>`. Check every template in `ar`.
- **Ordering.** Sections loop over `section.blocks` (spec 4 §2.4). Fixed parts are static blocks.
- **Cart and variants.** Use `window.commera` and never re-implement cart calls. Checkout and account
  pages are Commera's, and themes only style them through `theme` settings and CSS variables.
- **Apps.** Main sections set `accepts_apps` where apps add value (product information, cart). Never
  hard-code an app's markup.
- **Budgets.** No section adds more than 10 KB of JS. Images go through `image_url` with explicit
  widths, and the largest image on a page is not lazy-loaded.
- **Accessibility.** Interactive controls are real buttons or links, images have `alt` from the data,
  and colour contrast meets 4.5:1 using the theme's own settings.

### 3.4 Keeping it in step with the code

- **Generated references.** The skill's reference files (`references/context.md`,
  `references/schema.md`, `references/check-rules.md`, `references/storefront-js.md`) are generated at
  build time from the SDK dataclasses, `section.schema.json`, the check rule registry and
  `commera-storefront.d.ts`. Only `SKILL.md` is hand-written.
- **Versioned with the SDK.** The skill carries the `commera.sdk` version it was generated for. The
  CLI warns when a project's installed skill is older than the installed Commera.
- **Tested with evals.** CI runs an agent against three fixed briefs (a fashion store, an Arabic-first
  grocery store, and a one-product brand) on a demo site, and records `theme check` findings, test
  results and screenshots. A skill change that increases findings fails review.

### 3.5 Distribution

| Where | How |
| --- | --- |
| In a developer's app | `bench commera agent install [--app A]` copies both skills into `A/.claude/skills/` and writes or updates an `AGENTS.md` section pointing to them. It is idempotent, and `--check` reports whether they are stale. |
| New themes | `bench commera theme new` runs `agent install` for the app unless `--no-agent` is passed. |
| On the web | The docs site publishes the same skills and an `llms.txt` index. Commera already serves `/llms.txt` for storefronts; the developer docs get their own. |

## 4. Apps get the same treatment

Everything above applies to apps built on spec 1:

- **Generators.** `bench commera new-extension` scaffolds apps (spec 1 §5).
- **Machine-readable output.** `extensions validate --json` and `extensions list --json` give an
  agent what `theme check --json` and `theme describe` give it for themes.
- **Types.** `extensions types` gives completion for `@commera/admin`.
- **Seeing the result.** `bench --site X commera extensions render --target T --out file.png`
  screenshots a dashboard target with the app's extensions mounted, for the same reason as
  `theme render`.
- **Guidance.** The `commera-app` skill carries the order hook contracts (after commit, background
  job, system user) and the isolation rules from spec 2, which are the two things agents most often
  get wrong.

## 5. Phases

| Phase | Ships | Depends on |
| --- | --- | --- |
| A1 | `commera.sdk.storefront` types, page context refactor of the storefront controllers, `window.commera` and its `.d.ts` | spec 4 T1 (engine) |
| A2 | `--json` everywhere, `theme context`, `theme describe`, check rule ids and fixes | spec 4 §2.5 CLI |
| A3 | `theme render` (headless Chromium), `demo-data` presets | A1 |
| A4 | `commera-theme` skill with generated references, `agent install`, the evals in CI | A1–A3 |
| A5 | `commera-app` skill, `extensions render` | spec 1 P-phases |

A1 is worth doing without agents: it removes the per-controller context dicts and the inline queries
that make themes fragile today.

## Open questions

- **MCP server.** Should `bench commera mcp` expose `context`, `describe`, `check` and `render` as
  tools, for agents that prefer MCP over a shell?
- **Figma or screenshot input.** Should the brief accept reference screenshots, with a rule for how
  closely to match them?
- **Builder themes.** Should the same brief format drive Bob when creating a Builder theme ("Describe
  it" in spec 6 §3.1), so that one brief works for both kinds?
- **Eval ownership.** Who reviews eval screenshots when the skill changes, and what counts as a
  regression beyond `theme check` findings?
