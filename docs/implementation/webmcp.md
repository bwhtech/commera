# WebMCP tools

[WebMCP](https://developer.chrome.com/docs/ai/webmcp) lets a page register tools that an AI agent in the shopper's browser can call. The agent gets structured data back and does not need to read the page or click on it. Commera registers its tools on every themed storefront page. The tools act in the shopper's own tab and session.

## Where the code is

| Part | File |
|---|---|
| Registration and results | `packages/storefront/webmcp/index.js` |
| Catalog and cart tools | `packages/storefront/webmcp/storefront_tools.js` |
| Checkout tools | `packages/storefront/webmcp/checkout_tools.js` |
| Store page tools | `packages/storefront/webmcp/page_tools.js` |
| Registration call | `commera/public/js/commera-storefront.bundle.js` |
| `webmcp` and `localization` in `window.commera_storefront_config` | `build_base_context` in `commera/shop_themes/theme_resolver.py` |
| Tests | `packages/storefront/test/webmcp.test.js`, `packages/storefront/test/webmcp-checkout.test.js`, `packages/storefront/test/starter-checkout.test.js` |

Each tool is a thin wrapper around a function of the storefront SDK. The tools do not call the API themselves. Cart tools go through the SDK, which sends `commera:cart-updated`. The Commera Starter cart and the shared cart store in `commera/templates/includes/cart-state.html` (Summer Theme, Shop Base Theme) listen and show the new cart. The shared store first waits for its own sync, then takes the server cart, as it does on a version conflict.

Every SDK call on a page in another language than the default sends that language as `_lang`, so replies and the checkout handoff use `/ar/` on the Arabic storefront even when the account or browser prefers English. Without `_lang`, a storefront API call replies in the default language. Tools build page links with `url()` from `packages/storefront/localization.js`, which adds the page's language prefix as the Python `url()` does.

## Tools

| Page | Tools |
|---|---|
| Every storefront page except checkout | `search_catalog`, `browse_store`, `get_product`, `show_product`, `get_cart`, `update_cart`, `clear_cart`, `proceed_to_checkout` |
| `/cart/checkout`, or `/<language>/cart/checkout` in another language | `get_checkout`, `update_checkout`, `complete_checkout`, `navigate_to_storefront` |
| Every storefront page, checkout too | `list_store_pages`, `get_store_page` |

- A tool returns `structuredContent` and the same data as JSON text in `content`.
- A `StorefrontError` becomes a tool result with `isError: true` and the error message. Other errors are thrown, because they are bugs.
- `update_cart` sets the cart to exactly the lines it gets with one `cart.set_lines` request. The server compares the `revision` from `get_cart` with the cart and raises `CartChangedError` if they differ; the tool then returns the current cart with `changed: false`. The cart's `revision` counts every save, and `clear_ordered_cart` raises it too, so a write read before an order was placed is refused. The cart's `version` (its modified time) stays for the shared cart store's sync, which needs order cleanup to leave it alone. The server cart row is locked while it checks and saves. `set_lines` locks the open checkout first and is refused while a payment for the cart is open.
- Tools that only read store data have `readOnlyHint` and `untrustedContentHint`, because product text comes from the merchant. Cart writes return the same text, so they have `untrustedContentHint` too.
- `update_checkout` sends `commera:checkout-updated` after each step it saves, so the page shows a saved address even when a later shipping option fails. The Commera Starter checkout listens and shows the change, including a move between pickup and delivery. The Summer Theme checkout uses older endpoints, so it shows the change only after a reload.
- `list_store_pages` and `get_store_page` read published Shop Web Pages (policies, FAQ, contact) through `shop.list_pages` and `shop.get_page`. The agent reads the merchant's own text. `shop.get_page` returns the Arabic content on the Arabic storefront and falls back to English when a page has none.
- `complete_checkout` has `consequentialHint`. It reads the checkout itself and asks the buyer in a `confirm` dialog that shows its items, delivery, email, payment method and total. The items and currency come from the same checkout state as its `version`. It then starts payment with that total and the checkout `version`. The version is a digest of what the buyer approves: lines, email, addresses, pickup or delivery option, and total (`get_checkout_version` in `commera/api/payments.py`). It follows the content, not timestamps, so an address edited in place counts. The server refuses the payment if the checkout changed since, even when the total is the same. Cash on delivery is placed later, on `complete`. Every cash on delivery start writes the Quotation's hidden `custom_reviewed_checkout` and `custom_reviewed_total`: the reviewed version and payable total when an agent started it, empty when the shopper paid from the page. `place_cod_order` refuses a checkout that no longer matches the version, and, after it reprices, a total other than the reviewed one. These live on the quotation, so a lost cache key cannot skip either check, and `complete` still finds the cash on delivery start. The dialog prints amounts with `format.money_text`, which writes the currency code where the symbol is HTML (SAR). For gateway payments the version binds the start of payment only; a saved address can still be edited while the payment is pending. Cash on delivery places the order. Other methods open the payment page, where the buyer pays. A browser automation agent can still accept the dialog itself, so the dialog proves the order details, not who clicked.

## Turn it off

Clear Commera Settings > SEO > Crawlers & AI > Enable WebMCP Tools for Browser AI Agents. It is on by default.

## Try it

Use a browser with WebMCP, for example Chrome with `chrome://flags/#enable-webmcp-testing` or `agent-browser`:

```sh
agent-browser open https://<site>/products
agent-browser webmcp list
agent-browser webmcp invoke search_catalog --params '{"query": "brake"}'
```

## Not done yet

- Tools for account, orders and wishlist.
- Pages that the theme engine does not render do not load the SDK, so they have no tools.
