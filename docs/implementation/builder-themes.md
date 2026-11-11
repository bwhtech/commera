# Builder themes (POC)

A Builder theme is a Shop Theme whose home, product listing and product detail pages are Frappe Builder pages. The merchant designs them by prompting Bob, Builder's AI assistant. Cart, checkout, account and every other page render from the parent theme (the Sections starter), and are not themeable in Builder.

## Flow

1. Dashboard → Themes → New theme (shown when the `builder` app is installed) calls `commera.api.admin.theme.create_builder_theme`.
2. `commera.builder_themes.theme.create_builder_theme` creates a Builder Project Folder named after the theme and three empty Builder Pages in it, then a Shop Theme of type `Builder` whose `builder_pages` table maps each page type to its page.
3. The dashboard opens the home page in the Builder editor. The merchant prompts Bob there, page by page, and publishes in Builder.
4. Switch Theme makes it live. Unpublished pages fall back to the parent theme.

## Source of truth

| Concern | Owner |
| --- | --- |
| Which page plays which role | `Shop Theme.builder_pages` (`Shop Theme Builder Page`), read by `commera.builder_themes.pages` |
| Serving the storefront routes | `commera.builder_themes.renderer.BuilderThemePageRenderer`, a `page_renderer` before `ThemePageRenderer`. It matches the Shop Themed Routes for `pages/index.html`, `pages/products/list.html` and `pages/products/details.html`, and hands the mapped, published page to Builder's `BuilderPageRenderer`. |
| Page data | `commera.builder_themes.page_data.get_page_data`, Builder's `builder_page_data` hook. The editor canvas, Bob and the live page all read it. |
| Bob's instructions | `commera.builder_themes.agent_context.get_agent_context`, Builder's `builder_agent_context` hook |
| Storefront SDK and behaviours on the page | Each page's `head_html` is `{{ commera_builder_head() }}` (`commera.builder_themes.head`): the SDK bundle plus `public/js/commera-builder.js` |

Builder binds keys, not expressions, so page data is display-ready: prices are formatted strings, images are sized URLs, and every product, filter, sort and page link is a finished URL (`commera.builder_themes.listing.Listing`). The add-to-cart button binds `data-commera-add-to-cart` to `commera.product.default_variant_id`, so the behaviours script needs no page data of its own.

## Behaviour attributes

`commera-builder.js` wires plain Builder blocks by attribute:

- `data-commera-cart-count`: text becomes the cart's `total_quantity`.
- `data-commera-size="<variant id>"`: a size button; the chosen one gets `aria-pressed="true"`.
- `data-commera-add-to-cart`, `data-commera-buy-now`: add the chosen size (or `default_variant_id`), then show the result in `data-commera-cart-message` or go to checkout.
- `data-commera-checkout`: go to checkout.

After a successful add, the window fires `commera:cart-added` with the cart. A cart drawer is the theme's own: Bob designs it and writes it as a shared page script (`window.commera.cart` for reads and writes, `commera:cart-updated` for changes), built once on Home and attached on the other pages. `agent_context.CART_DRAWER` gives Bob that contract.

## Theme bar (Builder plugin)

The theme bar is a Builder editor plugin: a "Theme · Page" button in the toolbar on pages of a Commera theme. Its popover switches between the theme's three pages (each with Published, Edited or Draft), picks the product or collection the canvas previews (it sets the page's route variables), publishes the theme, makes it live, and opens the page on the store. It lives in [bwhtech/commera-builder-plugin](https://github.com/bwhtech/commera-builder-plugin) as one plain ES module, and the merchant installs it from the Builder Hub catalog. Its API is `commera.api.admin.builder_theme`, its logic `commera.builder_themes.editor`. Publish theme skips a page that has nothing built yet, so its route keeps rendering from the parent theme.

## Builder changes

Two hooks and one editor fix, merged in [frappe/builder#1075](https://github.com/frappe/builder/pull/1075):

- `builder_page_data`: `BuilderPage.get_app_page_data` puts each app's dict under the app's name (`commera`), before the page's own data script runs. Bindings read `commera.product.title`.
- `builder_agent_context`: `AgentRunner.build_agent_context` adds each hook's text for the open page to Bob's context.
- The editor (`pageStore.setPageData`) fetched page data only for pages with a data script, so the canvas showed hook data as empty. It now always fetches. With no route variable set, the product page previews the newest product; type a handle into the page's `route` variable to preview another.

## Known gaps

- Bob builds one page per session. The merchant opens each page and prompts it; the listing and product pages match the home page by instruction.
- Design tokens are site-wide in Builder. Bob is told to prefix them with the theme slug; nothing enforces it.
- Builder pages also answer at their own `ct/<theme>/...` routes, and those routes are indexable too.
- SEO comes from the Builder page, not the product: every page's title is its Builder page title, the canonical URL is the route rule's target, and a product's noindex, meta description, hreflang alternates and JSON-LD are not rendered. Builder nests the hook's data under `commera`, so page data cannot set Builder's top-level `metatags`; fixing it needs a Builder change.
- Deleting a theme leaves its Builder folder and pages, so a new theme with the same name is refused until they are deleted in Builder.
- One language: the `ar` routes render the same blocks.
- The listing ignores the `subcategory` parameter that menu links carry.
