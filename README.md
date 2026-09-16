<div align="center" markdown="1">

<img src="commera/public/images/commera.svg" alt="Commera logo" width="80" />
<h1>Commera</h1>

**Open source storefront and merchant dashboard for ERPNext**

<a href="https://buildwithhussain.com"><img src=".github/built-at-bwh.svg" alt="Built at BWH" height="28" /></a>

<div>
	<img width="1402" alt="Commera storefront" src=".github/screenshots/storefront.png">
</div>

</div>

## Commera

Commera turns an ERPNext site into a complete online shop. Shoppers get a fast, bilingual, themeable storefront rendered server-side; the people running the shop get a modern dashboard built with Vue 3 and Frappe UI. ERPNext stays the system of record underneath, so stock, pricing, tax and accounting are never a second copy that drifts.

### Motivation

Most ERPNext storefronts make you choose. Either you take a server-rendered portal that is quick and SEO-friendly but painful to administer, or you bolt on a separate storefront platform and spend the rest of the project reconciling two catalogues, two stock counts and two sets of orders.

Commera refuses that trade. The storefront is Jinja, Tailwind and Alpine — no SPA payload between a shopper and a product page — while the merchant side is a proper single-page app that feels like the commerce tools people already use. Both read and write the same ERPNext documents.

### The Merchant Dashboard

<div>
	<img width="1402" alt="Commera merchant dashboard" src=".github/screenshots/dashboard.png">
</div>

A Vue 3 + [Frappe UI](https://github.com/frappe/frappe-ui) app served at `/commera`, and registered on the desk apps screen so it sits alongside ERPNext.

- **Overview** — Revenue, order counts and what needs fulfilling, against the previous period.
- **Orders** — Filter by unfulfilled, unpaid, open or closed; drill into payment and fulfilment state per order.
- **Products** — Templates, variants, pricing and inventory, including bulk publishing and bulk image upload.
- **Customers, Collections and Attributes** — The catalogue structure, editable without touching the desk.
- **Analytics** — Revenue, inventory and first-party storefront funnels.
- **Storefront** — Switch theme, build the navigation menu, and edit content pages with live preview.

### Payments, Shipping and Analytics

> Payments and shipping are provided by two companion apps, [**bwh_payments**](https://github.com/bwhtech/bwh_payments) and [**bwh_shipping**](https://github.com/bwhtech/bwh_shipping). Both are required alongside ERPNext.

Providers are configured from the dashboard rather than the desk. Each keeps its own credentials, and each can be switched on independently.

#### Payments

- **Razorpay** — Cards, UPI, netbanking and wallets. India.
- **Stripe** — Cards and wallets, worldwide.
- **Telr** — Cards and local methods across the GCC.
- **Tabby** — Buy now, pay later in four instalments. MENA.
- **Cash on delivery** — With its own fee, a threshold above which the fee is waived, and the account it books to.

Gateway callbacks are idempotent, so a replayed webhook racing a shopper's return cannot bill twice.

<div>
	<img width="1402" alt="Payment providers and cash on delivery settings" src=".github/screenshots/payments.png">
</div>

#### Shipping

- **Shiprocket** — Courier aggregator for domestic India, with pincode serviceability.
- **AfterShip** — Global labels and tracking across hundreds of carriers.

Each carrier quotes its own rates at checkout, and delivery options control what shoppers actually pick from.

<div>
	<img width="1402" alt="Shipping carriers and delivery options settings" src=".github/screenshots/shipping.png">
</div>

#### Analytics

- **Storefront tracking** — First-party, powers the Storefront report, and nothing leaves the site.
- **Google Analytics 4** — The storefront reports `page_view`, `view_item`, `add_to_cart`, `begin_checkout` and `purchase`. Add a service account alongside the measurement ID and the dashboard reads the numbers back through the GA4 Data API.
- **Meta** — The pixel reports `PageView`, `ViewContent`, `AddToCart`, `InitiateCheckout` and `Purchase`, and an access token lets the dashboard read those counts back from the Graph API.

Both connections are optional and off until their keys are filled in. Because the dashboard reads the counts back rather than only sending them, the funnel sits next to your own revenue figures instead of living in another tab.

<div>
	<img width="1402" alt="Analytics and marketing connections" src=".github/screenshots/analytics.png">
</div>

### Key Features

- **Bilingual, RTL-ready storefront.** URL-based language switching (`/en/`, `/ar/`) on Frappe's native translation system, with right-to-left layout handled throughout rather than patched on.

- **Themeable without forking.** Themes are data: a `Shop Theme` record plus a template directory. A theme declares its own routes, may require auth per route, and can override any page the app ships — so a shop can restyle checkout without maintaining a fork.

- **Style Attribute Configurator.** Model a garment once as a template with colour and size attributes, then generate and publish its variants in bulk instead of hand-creating each SKU.

- **Returns and refunds.** Return reasons, return delivery notes and partial refunds booked back through ERPNext.

- **Search.** A configurable index over the catalogue with per-field content and result mapping, rebuilt nightly.

- **SEO and AI discoverability.** Per-page metadata, generated `sitemap.xml`, `llms.txt`, and Open Graph images rendered from templates at request time.

- **Merchandising.** Landing page hero banners, promo banners, recommended variants, size charts and back-in-stock notifications.

### Under the Hood

- [Frappe Framework](https://github.com/frappe/frappe) — Full-stack Python web framework.
- [ERPNext](https://github.com/frappe/erpnext) — Stock, pricing, tax and accounting.
- [Frappe UI](https://github.com/frappe/frappe-ui) — Vue 3 component library for the dashboard.
- Jinja, [Tailwind CSS](https://tailwindcss.com) and [Alpine.js](https://alpinejs.dev) for the storefront.

## About BWH Studios

Commera is developed and maintained by BWH Studios, a tech company based in Jagdalpur, Chhattisgarh, specializing in Frappe customizations and consulting.

---

<div align="center">

Let's make it the best open source eCommerce platform ✌️

</div>
