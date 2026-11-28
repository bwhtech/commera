---
name: commera
description: Commera online store data model (products, options, sizes, prices, stock, collections, orders, customers, discounts, reviews) and the Commera APIs for common tasks. Use when the user asks about their store, products, prices, stock, orders, sales, discounts or reviews, or asks to change any of them.
---

# Commera

Commera is an online store built on ERPNext. Read this before you touch any product, price, stock or discount record.

## Data model

```
Item (product template, has_variants=1)       name = item_template
 ├─ Style Attribute Configurator              the option axis, e.g. Colour
 └─ Style Attribute Variant                   one option, e.g. "Tee - Red": what is published and priced
     └─ sizes (Color Size Item)               size + item_code → a real size Item that is sold
```

- **Product**: an `Item` template. Its `name` is the `item_template` that the product APIs take.
- **Option**: a `Style Attribute Variant`. It has `is_published`, `route` (storefront page `/products/<route>`), `images` and a `sizes` table. A product with no options has one option called One Size.
- **Price**: an `Item Price` on each size Item, on two price lists from Commera Settings. `default_price_list` is the regular (compare-at) price, `sale_price_list` is the sale price. The shopper pays the sale price when it is set.
- **Stock**: the `Bin` of each size Item in `Commera Settings.ecommerce_warehouse`. The low-stock level is `Item.safety_stock`.
- **Collection**: a leaf `Item Group`. A product's collections are in `Item.custom_collections`; `Item.item_group` is the main one.
- **Order**: a `Sales Order`. Fulfilling it submits a Delivery Note.
- **Customer**: a `Customer`. The store's private note is in `customer_details`.
- **Discount**: a `Commera Discount` (not Pricing Rule or Coupon Code). Its codes are `Commera Discount Code` rows. `status` (Active, Scheduled, Expired, Used Up, Disabled) and `budget_left` are computed, not stored.
- **Review**: a `Product Review` on an option (`variant`), with `rating`, `comment`, `is_published` and `seller_reply`.

## Rules

- **Never `create`, `update` or `delete` an Item, Item Price, Bin, Style Attribute Variant, Style Attribute Configurator, Stock Entry, Delivery Note or Commera Discount with the generic record tools.** A product is many linked records. The Commera APIs below create the size Items, price rows and publish checks together. A direct write leaves a broken product.
- Use the Commera APIs with `call_api` for products, prices, stock, orders, discounts and reports. Each one in the Read table runs without asking the user.
- Use `read_records` for customers, reviews, collections and plain order lookups (see Read).
- Every write needs the user's approval. Say what will change, with prices and quantities, before you call it.
- Money is in the store currency. Never guess a price or a quantity. Ask.
- Read at most 50 rows in one call. Page with `start` and `page_length`.

## Read

Commera APIs (`commera.api.admin.` + ...), all read-only:

| Task | API |
|---|---|
| Store overview: revenue and order stats, recent orders, stock running low, options that need attention | `orders.get_overview()` |
| Orders | `orders.get_orders(status, search, start, page_length)`. `status` is open, unfulfilled, unpaid, fulfilled, closed or cancelled, or empty for all. |
| One order with its lines, payment and fulfilment stage | `orders.get_order(sales_order)` |
| Products | `catalog.get_products(search, collection, published, start, page_length)` |
| One product with its options, sizes, prices, stock and recent sales | `catalog.get_product(item_template)` |
| Best sellers | `catalog.get_top_products(limit)` |
| Prices of every option and size | `catalog.get_pricing_rows(search, collection, start, page_length)` |
| Stock | `inventory.get_inventory(availability, search, start, page_length)` |
| Recent stock received | `inventory.get_stock_movements(start, page_length)` |
| Discounts | `discounts.get_discounts(tab, search, start, page_length)` |
| One discount with its performance | `discounts.get_discount(name)` |
| Sales, inventory value, storefront traffic by month | `analytics.get_revenue_report(months)`, `analytics.get_inventory_report(months)`, `analytics.get_storefront_report(months)`. System Manager only. |

With `read_records`:

| Task | DocType and fields |
|---|---|
| Find a customer | `Customer` `{"customer_name": ["like", "%X%"]}`: `name`, `customer_name`, `email_id`, `mobile_no`, `customer_details` |
| A customer's orders | `Sales Order` `{"customer": <name>, "docstatus": ["<", 2]}`: `name`, `transaction_date`, `status`, `grand_total`, `per_delivered` |
| Reviews | `Product Review`: `name`, `variant`, `rating`, `review_title`, `comment`, `is_published`, `seller_reply`, `creation` |
| Collections | `Item Group` `{"is_group": 0}`: `name` |

## Write

Each write needs the user's approval. APIs are `commera.api.admin.` + ...

| Task | API |
|---|---|
| Create a product | `catalog.create_product(title, collection, option_attribute, size_attribute, option_sizes, price, sale_price)`. `option_sizes` is `[{"option": "Red", "sizes": ["S", "M"]}]`. Leave out options and sizes for a One Size product. |
| Rename, describe, disable, recollect | `catalog.update_product(item_template, title, description, disabled, collections)`. `collections` replaces all of them. |
| Add or remove options and sizes | `catalog.save_product_options(item_template, add, remove)`, each `[{"option": "Red", "size": "M"}]` |
| Publish or unpublish a product | `catalog.set_product_published(item_template, publish=1)`. Options that are not ready are skipped and listed. |
| Publish or unpublish one option | `catalog.set_variant_published(style_attribute_variant, publish=1)` |
| Price every size of an option | `catalog.set_variant_price(style_attribute_variant, default_rate, sale_rate)` |
| Price sizes one by one | `catalog.save_product_prices(style_attribute_variant, size_prices=[{"item_code", "default_rate", "sale_rate"}])` |
| Low-stock level | `catalog.set_restock_level(item_template, level)` |
| Receive stock | `inventory.receive_stock(received_quantities={item_code: qty})` |
| Collections | `catalog.create_collection(title)`, `catalog.add_products_to_collection(item_templates, collection)`, `catalog.remove_products_from_collection(item_templates, collection)` |
| Delete a product | `catalog.delete_product(item_template)`. Only works when it was never sold or stocked. Otherwise disable it. |
| Fulfil an order | `orders.fulfil_order(sales_order)` |
| Discount | `discounts.save_discount(discount)` with the shape `get_discount` returns (no `name` to create). `discounts.create_codes(name, count, prefix)` for unique codes. |
| Review | `reviews.set_published(name, published)`, `reviews.save_reply(name, reply)` |
| Customer note | `customers.save_customer_note(customer, note)` |

To change a product, read it with `get_product` first. Each item in `variants` is an option: its `name` is the `style_attribute_variant` the write APIs take, and each of its `sizes` has the `item_code`, `default_rate`, `sale_rate` and `stock`.

## Common requests

- **How is the store doing**: `get_overview`. For a month-by-month trend, `get_revenue_report`.
- **What is low on stock**: `get_inventory(availability="low")`. Suggest a quantity to receive, and receive it only after the user agrees.
- **Put X on sale**: find X with `get_products(search=X)`, read it with `get_product`, then `set_variant_price` with a `sale_rate` below the `default_rate` on each option.
- **Make a 10% code**: `save_discount` with `title`, `discount_type` "Amount Off Products", `method` "Code", `value_type` "Percentage", `value` 10, `enabled` 1 and the `code`. Read an existing discount with `get_discount` to copy the field names.

## Links

Link each record you mention. The dashboard is at `/commera`:

- Product: `/commera/products/<item_template>`
- Order: `/commera/orders/<sales_order>`
- Customer: `/commera/customers/<customer>`
- Discount: `/commera/discounts/<name>`
- Review: `/commera/reviews/<name>`
- Collections, inventory, pricing: `/commera/collections`, `/commera/inventory`, `/commera/pricing`
