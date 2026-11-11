# Localized themes

A store can publish its storefront in more than one language. This guide tells a theme developer how to write templates that work in every published language. `bench commera theme new` writes templates that follow these rules.

## Languages

The merchant sets the default language and the published languages in Commera Settings. The URL alone sets the language of a page:

| URL | Language |
| --- | --- |
| `/products/linen-shirt` | The default language |
| `/ar/products/linen-shirt` | Arabic |

The default language has no prefix. Each other published language has its code as the first path segment. Commera removes the prefix before the page route resolves, so a theme has one `pages/products/details.html` for every language.

Every theme page and section gets a `localization` object. Outside a theme page, such as in a plugin block or a macro, call `get_localization()`. Both give the same object:

| Field | Value |
| --- | --- |
| `localization.language` | The language of this page |
| `localization.default_language` | The default language of the store |
| `localization.available_languages` | The published languages, default first |

Each language has `code` (`ar`), `name` (`Arabic`), `endonym` (`العربية`) and `direction` (`ltr` or `rtl`).

The base template sets the `lang` and `dir` attributes of `<html>` from `localization.language`. Keep them in your own `components/base.html`:

```jinja
<html lang="{{ localization.language.code }}" dir="{{ localization.language.direction }}">
```

## Interface text

Write each piece of interface text in `_()`:

```jinja
<button type="submit">{{ _("Add to cart") }}</button>
<p>{{ _("{0} items").format(count) | e }}</p>
```

`_()` reads the translation files of the installed apps, such as `commera/translations/ar.csv`. Put the translations of your theme strings in the translation files of your app. Write each string as one literal inside `_()`, so that Frappe's string extraction finds it. Commera ships Arabic for the starter theme, the SDK, the storefront package and the dashboard. `bench commera check-translations --lang ar` lists the strings that have no Arabic yet.

Frappe Jinja does not escape a value for you. Add `| e` to a value that a merchant or a shopper can change.

## Links

Write every link to a storefront page through `url()`:

```jinja
<a href="{{ url('/products') | e }}">{{ _("Shop all") }}</a>
<a href="{{ url(section.settings.button_url or '/products') | e }}">{{ section.settings.button_label | e }}</a>
```

`url(path)` gives `path` in the language of the page. On an Arabic page, `url('/products')` gives `/ar/products`. On a default-language page, it gives `/products`. A path that already names a language moves to the language of the page.

`url()` does not change these links:

- Links to another site.
- Relative links, such as `details` or `#reviews`.
- Paths that are not storefront pages: `/api/`, `/assets/`, `/files/`, `/app/` and the like.

A `javascript:`, `data:` or `vbscript:` link becomes `#`.

Do not build a language prefix by hand. A template such as `"/" ~ localization.language.code ~ "/products"` gives a wrong link for the default language and for a language that is not published.

### Link to another language

`switch_url(path=None, query=None, language=None)` gives a page in another language:

```jinja
<a href="{{ switch_url(language='ar') | e }}" hreflang="ar">العربية</a>
<a href="{{ switch_url('/products', query={'sort': 'newest'}) | e }}">{{ _("Newest") }}</a>
```

Without `path`, it gives the current page with its query. Without `language`, it uses the language of the page. A language that the shopper cannot open gives the default language.

### Language switcher

Commera has a macro that lists the published languages. Each item links to the current page in that language. It shows nothing for a store with one language.

```jinja
{% from "templates/macros/language_switcher.html" import language_switcher %}
{{ language_switcher(class="flex gap-2", link_class="px-2", current_class="font-medium") }}
```

A pick also sets the `preferred_language` cookie. The URL still sets the language of the page.

### Alternate URLs

The `seo` block of the base template writes one `hreflang` tag for each published language. Keep `{% block seo %}` in your base template.

`commera.localization.alternates(path=None)` gives one absolute URL for each published language.

Call `alternates()` in a page controller (`.py`) when you need the URLs yourself:

```python
from commera.localization import alternates

def get_context(context):
	context.alternates = alternates()  # [{"lang": "ar", "href": "https://…/ar/…", "x_default": False}, …]
```

It gives an empty list for a store with one language.

## Translated SDK objects

The `commera` SDK object gives store content in the language of the page. You do not translate it in the template:

```jinja
{% set product = commera.catalog.get_product(handle) %}
<h1>{{ product.title | e }}</h1>
```

These objects come translated: products, product cards, cart lines, collections, menus, pages, the shop and SEO data. The values come from Content Translation records. A field without a translation falls back to `_()` of the source text, then to the source text.

`commera.format.product_url(handle)` gives a product link with the language prefix. Do not pass it through `url()` again.

## Money, numbers and dates

Format money, numbers and dates through `commera.format`. Each function uses the rules of the page language:

```jinja
{{ commera.format.money(product.price, product.currency) }}
{{ commera.format.number(review_count) }}
{{ commera.format.date(posting_date, "long") }}
```

| Function | Gives |
| --- | --- |
| `money(amount, currency=None)` | The amount with the currency symbol. The symbol goes before the amount in a left-to-right language and after it in a right-to-left one. Without `currency`, it uses the store currency. |
| `number(value, precision=0)` | The number with the digit grouping of the language. |
| `date(value, style="medium")` | The date in the language. `style` is `short`, `medium`, `long` or `full`. |

Do not join a currency symbol and an amount by hand.

## Right-to-left layout

Arabic, Hebrew, Persian and Urdu read from right to left. For these languages, `localization.language.direction` is `rtl` and the page has `dir="rtl"`. The browser then flips the text and the flow of the layout. Your CSS must flip with it.

Use the logical CSS properties. They follow the direction of the page:

| Do not use | Use |
| --- | --- |
| `margin-left`, `margin-right` | `margin-inline-start`, `margin-inline-end` |
| `padding-left`, `padding-right` | `padding-inline-start`, `padding-inline-end` |
| `left`, `right` | `inset-inline-start`, `inset-inline-end` |
| `text-align: left` | `text-align: start` |
| `border-left` | `border-inline-start` |
| `width`, `max-width` | `inline-size`, `max-inline-size` |

In Tailwind, use the logical classes: `ms-4`, `me-4`, `ps-4`, `pe-4`, `start-0`, `end-0`, `text-start`, `text-end`, `rounded-s` and `border-s`.

Flip an icon that points in a direction, such as an arrow, with the `rtl:` variant:

```jinja
{% from "components/macros/icons.html" import icon %}
<span class="rtl:-scale-x-100">{{ icon("right", "size-4") }}</span>
```

`icon` is a macro of the Commera Starter theme, not a Jinja global. Your theme must have `components/macros/icons.html`, or inherit it from a parent theme.

Do not flip icons that have no direction, such as a cart or a search icon. A theme page also gets `is_rtl`, which is true on a right-to-left page.

To check a template, publish Arabic in Commera Settings and open the page under `/ar/`.

## Plugin blocks

A plugin block in a storefront slot, such as `cart_banner`, also gets `localization`. Use `url()` and `_()` in it in the same way as in a theme.
