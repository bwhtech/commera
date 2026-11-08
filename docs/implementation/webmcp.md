# WebMCP tools

[WebMCP](https://developer.chrome.com/docs/ai/webmcp) lets a page register tools that an AI agent in the shopper's browser can call. The agent gets structured data back and does not need to read the page or click on it. Commera registers its tools on every themed storefront page. The tools act in the shopper's own tab and session.

## Where the code is

| Part | File |
|---|---|
| Tool definitions and registration | `packages/storefront/webmcp.js` |
| Registration call | `commera/public/js/commera-storefront.bundle.js` |
| `webmcp` and `language` in `window.commera_storefront_config` | `build_base_context` in `commera/shop_themes/theme_resolver.py` |
| Tests | `packages/storefront/test/webmcp.test.js` |

Each tool is a thin wrapper around a function of the storefront SDK. The tools do not call the API themselves. Cart tools go through the SDK, which sends `commera:cart-updated`. The Commera Starter cart and the shared cart store in `commera/templates/includes/cart-state.html` (Summer Theme, Shop Base Theme) listen and show the new cart. The shared store first waits for its own sync, then takes the server cart, as it does on a version conflict.

Every SDK call sends the page language as `_lang`, so replies and the checkout handoff use `/ar/` on the Arabic storefront even when the account or browser prefers English.

## Tools

| Page | Tools |
|---|---|
| Every storefront page except checkout | `search_catalog`, `browse_store`, `get_product`, `show_product`, `get_cart`, `update_cart`, `clear_cart`, `proceed_to_checkout` |
| `/<language>/cart/checkout` | `get_checkout`, `navigate_to_storefront` |

- A tool returns `structuredContent` and the same data as JSON text in `content`.
- A `StorefrontError` becomes a tool result with `isError: true` and the error message. Other errors are thrown, because they are bugs.
- `update_cart` sets the cart to exactly the lines it gets. It takes the `version` from `get_cart` and changes nothing if the cart changed after that read. The check runs in the browser, so it does not stop a change that occurs between the check and the write.
- Tools that only read store data have `readOnlyHint` and `untrustedContentHint`, because product text comes from the merchant. Cart writes return the same text, so they have `untrustedContentHint` too.

## Turn it off

Clear Commera Settings > SEO > Crawlers & AI > Enable WebMCP Tools for Browser AI Agents. It is on by default.

## Try it

Use a browser with WebMCP, for example Chrome with `chrome://flags/#enable-webmcp-testing` or `agent-browser`:

```sh
agent-browser open https://<site>/en/products
agent-browser webmcp list
agent-browser webmcp invoke search_catalog --params '{"query": "brake"}'
```

## Not done yet

- Checkout writes (contact, delivery, shipping option) and placing the order. Placing the order must use `consequentialHint` and ask the buyer to confirm.
- Tools for store policies and FAQs, account, orders and wishlist.
- Pages that the theme engine does not render do not load the SDK, so they have no tools.
