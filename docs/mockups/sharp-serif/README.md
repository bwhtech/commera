# Sharp serif theme mockup

A static HTML, CSS and JavaScript mockup for a possible new storefront theme. It is not a theme yet. Use it to decide if the direction is worth building as a Commera theme next to `commera_starter`.

The direction: sharp corners everywhere, hairline rules, black buttons and a warm off-white page. Geist Serif sets the display type and Geist Sans sets everything else. The red-orange accent is used only for sale prices.

## Pages

- `index.html`: home, with hero, collections, bestsellers, a story section and the newsletter
- `collection.html`: collection, with category chips, colour filters, sort and a product grid
- `product.html`: product, with a gallery, colour and size options, reviews and a sticky "Add to cart" bar on phones
- `cart.html`: cart, with quantity steppers, an order summary and a discount code
- `search.html`: search results, with sort and an empty state

The header search opens an overlay with live results. Press `/` to open it.

## Build and run

```bash
python3 build.py
python3 -m http.server 8766 --directory dist
```

`build.py` expands the partials and product cards in `src/` and writes the pages to `dist/`. It also writes `dist/catalog.js`, which the search and collection scripts read. `dist/` is not committed.

## Photos

The photos are CC0 or public domain images from Wikimedia Commons. See `img-source/CREDITS.md`. `img-source/` keeps the originals. `img/` keeps padded copies that fill the image frames:

```bash
python3 pad_images.py img-source img
```

The script needs ImageMagick.

## Open decisions

- The store name "Émail" is a placeholder.
- The review counts, delivery dates and product claims are sample content.
