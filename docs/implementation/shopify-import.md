# Shopify import — implementation plan

Status: proposal. Nothing is built yet.

## Goal

A merchant moves a Shopify store to Commera without manual work. They click "Connect Shopify", approve on Shopify, check a scan report, and click "Import". Commera then keeps the data up to date until the merchant moves the domain.

## Settled decisions

- **Connect, not upload.** The import reads the Shopify Admin GraphQL API. The CSV path is not built.
- **One Shopify app on Commera Cloud.** Commera Cloud (`https://cloud.commera.app`) holds the app and the client secret. The site keeps its own tokens. The connection spec is in the `commera_cloud` repository: `docs/shopify-connect.md`.
- **Bulk Operations for reads.** Each resource type is one `bulkOperationRunQuery`. The site downloads the JSONL file and imports it in a background job.
- **Every record keeps its Shopify ID.** A second run updates records and does not make duplicates. Later runs read only records with `updatedAt` after the last run.
- **Reuse `catalog.create_product`.** The import writes through the same functions as the dashboard. It does not write Items directly.
- **Shopify customer passwords are not needed.** Commera logs shoppers in with an emailed one-time code (`commera/sdk/auth.py:16`).

## What we take from aerele/shopify

Source: [aerele/shopify](https://github.com/aerele/shopify) at `df183c6`, GPL-3.0, which can be combined with Commera's AGPL-3.0. Keep the copyright note in each copied file.

| Take | From | Change |
|---|---|---|
| GraphQL product query and normalizer | `shopify/product.py` (`_PRODUCT_QUERY`, `_normalize_gql_product`) | Add media, SEO, handle, status, tags and metafields. Change to a bulk query. |
| GraphQL order normalizer | `shopify/order.py` (`_normalize_gql_order`, `_fetch_old_orders`) | Change to a bulk query. |
| Customer address mapping | `shopify/customer.py` (`_map_address_fields`) | None. |
| Weight UOM map | `shopify/constants.py` (`WEIGHT_TO_ERPNEXT_UOM_MAP`) | None. |
| Token refresh logic | `shopify/oauth.py` | Moves to Commera Cloud. |

Do not take: `ecommerce_core`, the `ShopifyAPI` package, `_create_item` and its variant code, webhooks, invoice, fulfillment and inventory push. They sync a live Shopify store with ERPNext. Commera needs a one-way move into its own product model.

## Flow

1. **Connect.** The site links to Commera Cloud, then runs the Shopify OAuth flow through it. The site stores the shop domain in `Shopify Connection` (single) and the tokens in Connected App and Token Cache.
2. **Scan.** A read-only pass counts each resource type and finds data that Commera cannot hold. The dashboard shows the report before anything is written.
3. **Import.** One background job per resource type, in this order: settings and branding, locations, collections, products, inventory, pages, navigation, customers, discounts, orders, redirects.
4. **Sync until cutover.** The merchant runs the import again. It reads only changed records.
5. **Cutover.** The dashboard shows a checklist: domain, payment gateway, shipping and taxes.

## Shopify to Commera mapping

| Shopify | Commera |
|---|---|
| Shop name, email, phone, currency | `Commera Settings`: `store_name`, `contact_email`, `contact_phone`. Currency comes from the Company. Stop when it differs from the Shopify currency. |
| Theme settings (logo, favicon, colors) | `Commera Settings`: `brand_logo`, `favicon`, color fields |
| Location | Warehouse. Only `Commera Settings.ecommerce_warehouse` sells. |
| Product | Item template, Style Attribute Configurator, Style Attribute Variants |
| Option named Color or Colour | Option axis: one Style Attribute Variant (page) per value |
| Other option | `Size` axis: a Color Size Item row |
| Variant price and compare-at price | Item Price on each size Item, through `save_size_prices` (`style_attribute_variant.py:134`) |
| Product description | `Item.description` |
| Vendor | `Item.brand` |
| Media | Images on each Style Attribute Variant |
| Handle | `Style Attribute Variant.route`, plus a redirect from `/products/<handle>` |
| SEO title and description | `meta_title`, `meta_description` on each Style Attribute Variant |
| Status draft, active, archived | `is_published`, `Item.disabled` |
| Collection | Item Group, plus an Ecommerce Category for the storefront |
| Customer | Customer, Contact, Address, User |
| Order | Sales Order. The import must not send emails, fire plugin events or move stock. |
| Discount code and automatic discount | Commera Discount, Commera Discount Code |
| Page | Shop Web Page |
| Menu | Ecommerce Category tree, Footer Section Config |
| URL redirect | `Website Settings.route_redirects` |
| Policies | Shop Web Page |

## Gaps in Commera

Evidence paths are relative to the repository root.

### Blocks the product import

| # | Gap | Evidence | Fix |
|---|---|---|---|
| G1 | The template takes 2 attributes only, and the second must be named `Size`. Shopify allows 3 options with any name. | `commera/api/admin/catalog.py:1188`, `:1212` | First: join options 2 and 3 into the size label, for example "M / Cotton", and show a warning. Later: let the second axis be any attribute and allow a third. |
| G2 | A single option that is not a color (for example Material) makes one page per value. | `catalog.py:1130-1172` | Add a rule that chooses which option makes pages. All other options go to the size picker. |
| G3 | An Item is named after its title, and a repeated title is refused. Shopify titles are not unique. | `catalog.py:1157` | Name Items by a naming series or the handle. Keep the title in `item_name`. |
| G4 | `create_product` cannot set SKU, barcode, weight or brand. | `catalog.py:1218` | Add the parameters. The Item fields exist. |
| G5 | Images live only on each Style Attribute Variant. There are no product-level images. Alt text is not shown. Video is not supported. | `commera/templates/macros/item_card.html:43` | Copy product images to each page. Show alt text. Video later. |
| G6 | A page without images and sizes cannot be published. | `catalog.py:701-707` | Attach images before publish. List products without images in the scan report. |
| G7 | A route is set from `scrub(name)` only when empty. | `commera/commera_ecommerce/doctype/style_attribute_variant/style_attribute_variant.py:57` | Set the route from the handle and the option value. Add a redirect for each page. |

### Data that is lost or flattened

| # | Gap | Evidence | Fix |
|---|---|---|---|
| G8 | A product has one collection (`Item.item_group`). A Shopify product can be in many. | `commera/utils.py:295` | Add a many-to-many link from collection to product. This is the largest model change. |
| G9 | No smart collections. | — | First: import each smart collection as a fixed product list. Later: a rule engine. |
| G10 | No product tags, product type or metafields. | — | Add tags. They also feed smart collections and filters. Map type to a field. Metafields become Custom Fields, with a way to show them. |
| G11 | No collection description. No manual product order in a collection. | — | Add both. |
| G12 | The storefront sells from one warehouse. | `commera/api/cart.py:27` | First: import the primary location. Later: add stock across warehouses. |
| G13 | No "continue selling when out of stock". | `commera/api/cart.py:39` | Add a flag on the product. |
| G14 | No customer tags. No marketing consent ([#124](https://github.com/bwhtech/commera/issues/124)). No Address helper outside the storefront account API. | `commera/core.py:115` | Add tags, consent fields and an Address helper. |
| G15 | Orders count in analytics, customer history and verified purchase only with `order_type == "Shopping Cart"`. "My orders" matches `owner`. Frappe overwrites `owner` and `creation` on insert. Status changes fire plugin events. | `commera/api/admin/orders.py:979`, `commera/order_access.py:85`, `commera/utils.py:845` | Add `imported_from`. Set `owner` and `creation` after insert. Skip events, emails and stock for imported orders. |
| G16 | Product Review is named by a hash of `variant` and `owner`, and has no reviewer name field. A bulk import as Administrator collides after one review per page. | `commera/commera_ecommerce/doctype/product_review/product_review.py:40` | Add `reviewer_name`. Change the naming. Reviews come from the review app's own export, not from Shopify. |
| G17 | Discount dates are Date, not Datetime. The per-customer limit is "once" only. | `commera/discounts/doctype/commera_discount/commera_discount.json` | Change to Datetime. Add a per-customer count. |

### Missing features

| # | Gap |
|---|---|
| G18 | Gift cards and store credit. Shopify also does not return full gift card codes, only the last characters. |
| G19 | Blogs and articles |
| G20 | Shipping zones by country and rates by weight. Commera has one Shipping Rule with price bands (`commera/api/admin/shipping_rates.py:24`). |
| G21 | Many currencies and markets. Languages are English and Arabic only. |
| G22 | A dashboard page for URL redirects. Frappe supports them, but Commera does not show them. |
| G23 | Subscriptions and bundles |

### Import plumbing

| # | Gap |
|---|---|
| G24 | No OAuth client and no Commera Cloud link on the site. |
| G25 | No background job with live progress. The spreadsheet import runs in the request (`commera/api/admin/imports.py:504`). Nothing calls `publish_realtime`. |

## Shopify cannot give

- Customer passwords. Not needed.
- Saved payment methods.
- Full gift card codes.
- The theme layout. It is Liquid code. We take only the logo, favicon and colors.
- Data from other Shopify apps, for example reviews, subscriptions and loyalty points. Each needs its own import.

## Steps

One PR per step. Each bullet is one commit.

### Step 1 — Connection and plumbing

- **S1-1 · Commera Cloud link** on the site: the identity token exchange and the API key. See `commera_cloud/docs/accounts-and-auth.md`.
- **S1-2 · `Shopify Connection`** single doctype and the connect flow through Commera Cloud (G24).
- **S1-3 · `Shopify Import Run`** doctype: status and counts for each resource type, an error table, and progress through `publish_realtime` (G25).
- **S1-4 · Bulk query runner:** start a bulk query, poll it, download the JSONL file, and give each line to an importer.
- **S1-5 · Scan report** in the dashboard. The Shopify tile in `dashboard/src/components/import/steps/SourceStep.vue:17` opens it.

### Step 2 — Products

- **S2-1 · `create_product`** gets Item naming by series (G3), SKU, barcode, weight and brand (G4).
- **S2-2 · Option mapping** with joined size labels for a third option (G1, G2).
- **S2-3 · Product importer:** products, prices, images, SEO, status, routes (G5, G6, G7).
- **S2-4 · Inventory** for the primary location (G12).
- **S2-5 · Redirects** from Shopify URLs, and a redirect page in the dashboard (G22).

### Step 3 — Store content

- **S3-1 · Settings and branding** from the shop and the theme settings.
- **S3-2 · Pages and policies** as Shop Web Pages.
- **S3-3 · Navigation** into the Ecommerce Category tree and the footer.

### Step 4 — Customers and orders

- **S4-1 · Customer fields:** tags, consent, Address helper (G14).
- **S4-2 · Customer importer.**
- **S4-3 · Imported order rules** (G15).
- **S4-4 · Order importer.**
- **S4-5 · Discount importer** (G17).

### Step 5 — Collections

- **S5-1 · Many-to-many collections** (G8, G11).
- **S5-2 · Tags and smart collections** imported as fixed lists (G9, G10).

Gaps G13, G16, G18 to G21 and G23 are separate projects. The scan report names them for each store.
