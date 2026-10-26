# Starter theme directions

Three design directions for the Commera starter storefront theme, built only on frappe-ui 1.0.2 tokens with Tailwind v4 and Alpine.js: Editorial minimal, Bold modern and Soft boutique. Each has a home, product list and product detail page.

Open `index.html` in a browser. The toolbar switches direction, page, phone width and dark mode.

A shareable copy (Vue port) is on Sketch: https://sketch.netchamp.dev/u/rl0007/commera-storefront-directions

Gaps the tokens do not cover:

- No orange Button or Badge theme.
- `surface-gray-10` turns light in dark mode, so it cannot be a fixed dark band.
- `surface-orange-1` looks muddy brown in dark mode.
- White text on `surface-blue-6` is slightly under WCAG AA.
- Colour swatches built from tokens flip in dark mode; real variant colours must be stored per product.
- The largest display size is 56px.
- There is no merchant brand colour token.
