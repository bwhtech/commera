# OG card templates

An OG card is the image that a link preview shows on social sites and in chat apps. Commera makes one card for each product and one card for the store:

| URL | Card |
| --- | --- |
| `/og-image/<handle>.jpg` | A product |
| `/og-image/<handle>.jpg?price=none` | A product without its price, for the pages of a secondary market |
| `/og-image/store.jpg` | The store: logo, name and tagline |

A card URL under a locale prefix, such as `/ar/og-image/<handle>.jpg` or `/en-ae/og-image/<handle>.jpg`, gives the card in that language and market. Pages put the card of their own language and market in `og:image`. The old `.png` URLs redirect to the `.jpg` card.

## How a card is drawn

A card is an HTML page of 1200 × 630 pixels. Frappe's headless Chromium, which also makes PDFs, takes a screenshot of the page and saves it as a JPEG. Commera keeps the image until the product, the store or the language text changes.

You can use full HTML and CSS: grid, flexbox, positioning, `-webkit-line-clamp`, gradients, logical properties and so on. The old renderer took only flexbox and a part of CSS. That limit is gone.

## Change the product card

Make an **OG Image Template** record for **Style Attribute Variant** and enable it. Its **Template HTML** replaces the bundled card, `commera/templates/og/product_card.html`. **Generate Preview** draws the template for a published product.

Start from the bundled card. It extends `commera/templates/og/base.html`, which sets `lang` and `dir` on `<html>`, loads the card fonts and sets the page size:

```jinja
{% extends "commera/templates/og/base.html" %}

{% block head %}
<style>
	.card { display: grid; place-items: center; height: 100%; background: #111; color: #fff; }
	.title { font-size: 64px; font-weight: 700; }
</style>
{% endblock %}

{% block body %}
<div class="card"><div class="title">{{ display_name | e }}</div></div>
{% endblock %}
```

A template can also be a full page of its own, or only a fragment such as `<div>…</div>`. Commera puts a fragment in `base.html`.

The product card gets these values:

| Value | Content |
| --- | --- |
| `display_name` | The product title, in the language of the card |
| `store_name` | The store name |
| `brand` | The brand, or empty |
| `price` | The price with the currency code, or empty for `?price=none` |
| `photo_url` | The first product photo, or empty |
| `doc` | The Style Attribute Variant |
| `lang`, `dir` | The language code and `ltr` or `rtl` |

The store card, `commera/templates/og/store_card.html`, gets `store_name`, `tagline`, `site_host`, `logo_url`, `lang` and `dir`.

## Rules

- Jinja does not escape values here. Write `| e` after every value, also in attributes: `{{ display_name | e }}`.
- Write the layout with logical CSS, such as `margin-inline-start` and `text-align: start`. A right-to-left card then flips by itself. See [Right-to-left layout](localization.md#right-to-left-layout).
- Images must be public files of the site (`/files/...`), assets (`/assets/...`) or `data:` URIs. The card cannot load an image or a font from another host, and it cannot read private files.
- The renderer serves the first document and public images and fonts from disk. It blocks later navigations, frames, objects, private files and remote requests, regardless of the requesting user.
- Scripts do not run. Cards and admin previews use JPEG quality 85.

## Fonts

`base.html` loads the card fonts from Commera's assets. The card does not use the fonts of the server.

- `OpenSans`: Open Sans, with IBM Plex Sans Arabic for Arabic text and IBM Plex Sans Hebrew for Hebrew text. Weights 400 and 700.
- `Commera Emoji`: Noto Color Emoji, for emoji only.

The page uses `font-family: "OpenSans", "Commera Emoji", sans-serif`. Keep `"Commera Emoji"` after your own font, or emoji do not show. To use your own font, add an `@font-face` rule with a `/assets/` URL in the `head` block.
