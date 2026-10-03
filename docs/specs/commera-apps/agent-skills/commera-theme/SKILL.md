---
name: commera-theme
description: Build or change a Commera storefront theme, including its sections, blocks, layouts, theme settings and page templates (home, product, collection, content pages, cart styling). Use it whenever the task touches files under an app's themes/ folder, or the user asks for a new storefront look, a new section, or an English/Arabic storefront. Not for dashboard extensions (use commera-app), and not for Frappe Builder themes (those are designed in Builder).
---

<!-- Draft for spec 7 (docs/specs/commera-apps/07-agent-ready-development.md). The references/ files
     named below are generated at build time from the installed Commera; they are not written by hand. -->

# Building Commera themes

A Commera theme is a folder of Jinja **sections**, each with a JSON **schema**, plus default
**layouts** that list which sections appear on each page, in order. Merchants reorder, hide and
configure sections in the dashboard's theme editor; you write the sections and their defaults.
Commera owns data, prices, translation, availability, the cart and checkout. The theme owns markup,
styles and layout.

```
<app>/themes/<slug>/
├── BRIEF.md             # you write this first (step 1)
├── settings.json        # global settings: colours, fonts, radius…
├── sections/<type>.html|.json|.py
├── layouts/index.json product.json collection.json page.json groups/header.json groups/footer.json
├── locales/en.json ar.json
└── assets/
```

## Workflow

Follow these steps in order. Ask the developer only in step 1, or when a rule below can't be
satisfied.

1. **Brief.** If `BRIEF.md` is missing, ask once for the store type, brand (colours, fonts, tone),
   languages, pages, must-have sections and reference sites. Write the answers to `BRIEF.md`. If
   the developer says "you decide", decide, and record your choices there.
2. **Survey.** Run `bench commera theme describe --theme <parent or existing> --json` to see which
   sections already exist, and `bench --site <site> commera theme context --template product --json`
   (and for `index`, `collection`, `page`) to see the exact data you can use. If the site has no
   products, run `bench --site <site> commera demo-data --preset <closest to the brief>` first.
3. **Plan.** In `BRIEF.md`, list each page's sections in order, with their blocks and settings.
   Reuse parent sections where they fit, and only create what the brief needs.
4. **Scaffold.** Use `bench commera theme new`, `theme new-section` and `theme new-block`. Do not
   hand-write schema JSON or block macros from scratch; edit what the generator wrote.
5. **Implement.** Write templates, CSS and controllers using only the data API below.
6. **Verify, and loop until clean:**
   - Run `bench commera theme check --theme <slug> --json` and fix every finding. Each has a `fix`.
   - For every template, run `bench --site <site> commera theme render --theme <slug> --template <t>`
     with `--lang en` and `--lang ar`, at `--width 1280` and `--width 390`, and look at every image.
     Fix overflow, broken RTL, contrast and empty states.
   - Run the app's tests (`assert_theme_valid`).
7. **Defaults.** Make `layouts/*.json` match the plan, so a fresh install looks like the brief.
8. **Report** to the developer: screenshots, the check summary, and anything you decided that a
   designer should review.

## Data: where everything comes from

Commerce data (products, prices, stock, collections, cart) comes from the page context or
`commera.sdk.storefront`; for exact fields, read `references/context.md` or run `theme context`.
For everything else you have the full Frappe API: the app's own DocTypes, `frappe.get_list`,
`frappe.get_cached_doc` and whitelisted methods. That is what lets a Commera theme do more than a
Shopify one.

| You need | Use |
| --- | --- |
| The current product, collection, content page or cart | `product`, `collection`, `page`, `cart` in the page context |
| Store name, logo, currency, languages | `store` |
| Language and direction | `request.language`, `request.dir` |
| Menus | `menus.main`, `menus.footer` (merchants edit these in Storefront → Navigation) |
| Theme settings | `theme.<id>` in templates, or `var(--theme-<id>)` in CSS |
| Other products or collections in a section | `sections/<type>.py` → `storefront.products(...)`, `storefront.collections(...)`, `storefront.recommendations(product)` |
| A price | `x.price.formatted` (a `Money`, already localised) |
| In stock? | `x.available` (Commera handles made-to-order items) |
| An image | `{{ image_url(x.image, width=600) }}` with `alt="{{ x.image.alt }}"` |
| Theme UI text | `{{ t("cart.empty") }}` with `locales/<lang>.json` |
| Your own records (lookbooks, store locations, size guides…) | Create a DocType in the app if needed. Load it in `sections/<type>.py` with `frappe.get_list` / `frappe.get_cached_doc`. Read its JSON to learn its fields. |
| A setting that points at one of your records | `{"type": "link", "doctype": "Lookbook"}` |
| Products listed in your own records | Take their handles from your record, then call `storefront.products(handles=…)` so prices and stock are right |
| A form, finder or booking | Call a whitelisted method in the app from the section's JS |

When you use Frappe directly:

- **Queries go in the controller**, never the template.
- **Storefront requests run as Guest or a customer.** Prefer `frappe.get_list`, which applies
  permissions. With `frappe.get_all`, filter to published records and return only public fields.
- **Cache expensive queries** with `frappe.cache` or `@redis_cache`, and clear the cache when the
  record changes.
- **Never read `Item Price`, `Bin` or `Item` fields for display.** Use Commera's objects, which
  apply price lists, customer prices, made-to-order items and translation.

## Sections and blocks

- Every section's template renders its blocks with
  `{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}`, so merchants can reorder
  them. Each block type is a `{% macro <type>(block) %}` in the same file.
- A part whose position is part of the design is a **static block** (`"static": true` in the
  schema), placed with `{{ render_static_block("<type>") }}`.
- Settings that hold customer-facing text are `"translatable": true`. Give every setting a sensible
  `default`, so a newly added section looks finished.
- Set `presets` so "Add section" inserts something useful, not an empty shell.
- Main sections (`main_product`, `main_collection`, `main_page`) are `"static": true`. Set
  `"accepts_apps": true` on `main_product` and wherever else apps could add value.
- Put loading in `sections/<type>.py` `get_context(section, page)`, never in the template.
- Keep a section to one job. Split a section with more than about 12 settings.

Schema keys and setting types are in `references/schema.md`. Your editor validates them through the
`$schema` line the generator writes.

## Browser behaviour

Use `window.commera` for anything with the cart or variants, and never call endpoints directly:

```js
await commera.cart.add({ variant, qty })   // emits commera:cart:updated
commera.product.select({ Size: 'M' })      // emits commera:variant:changed
```

Listen for `commera:cart:updated` to refresh the cart count or drawer. Handle `commera:cart:open` by
opening your cart UI, because app blocks dispatch it. Types are in `commera-storefront.d.ts` and
`references/storefront-js.md`. Keep each section's JS under 10 KB; Alpine stores wrapping
`commera.cart` are the house style.

## Rules

- **Commerce data comes from Commera.** Get prices, availability and catalogue text from the page
  context or `commera.sdk.storefront`, never from ERPNext DocTypes. Everything else is yours to
  build with Frappe.
- **Commera formats and translates.** Never format money, compute discounts, check stock, or
  hard-code customer-facing English.
- **Arabic is right-to-left.** Put `dir="{{ request.dir }}"` on `<html>`. Use logical CSS
  properties (`padding-inline-start`, `inset-inline-end`, `text-align: start`). Flip directional
  icons with `[dir=rtl]`. Check every template in `ar`.
- **Checkout and account pages belong to Commera.** Style them only through theme settings and
  CSS variables.
- **Merchant data lives in the site.** Never write Theme Layout records or edit a site's layouts.
  Your defaults go in `layouts/*.json`.
- **Never break the merchant's layouts.** Don't rename a section type or a setting `id` in a shipped
  theme. Add a new one, and let the old one fall back (`theme check` warns on renames).
- **Accessibility.** Use real `<button>` and `<a>` elements. Images get alt text from the data.
  Contrast must be at least 4.5:1 for the default settings. Focus must be visible.
- **Performance.** Pass explicit image widths. Don't lazy-load the main (largest) image. Don't use
  web fonts beyond the two in `settings.json`.

## When you're stuck

- A `theme check` rule you disagree with: don't suppress it. Report it to the developer with the
  rule id.
- Commerce data you need isn't in `theme context` (for example a price variant the SDK doesn't
  expose): tell the developer which key is missing. It belongs in `commera.sdk.storefront`.
- Non-commerce data the brief needs (store locations, lookbooks, FAQs): build it. Add a DocType to
  the app and load it in a controller.
- The brief conflicts with a rule (for example "hide prices"): follow the rule, and put the
  conflict in your report.

## References (generated for the installed Commera version)

- `references/context.md`: every page context object and its fields, with examples.
- `references/schema.md`: section schema keys, setting types, and how each renders in the editor.
- `references/check-rules.md`: every `theme check` rule id, why it exists, and how to fix it.
- `references/storefront-js.md`: the `window.commera` API and its events.
- `references/sections-cookbook.md`: worked examples of a hero slider, product grid, testimonials
  and a main product with app blocks.
