# Commera Currency Signs

`currency-signs.woff2` holds two glyphs:

| Code point | Name | Source artwork |
| --- | --- | --- |
| U+20C1 | SAUDI RIYAL SIGN (Unicode 17.0) | Saudi Central Bank (SAMA) |
| U+20C3 | UAE DIRHAM SIGN (Unicode 18.0) | Central Bank of the UAE (CBUAE) |

Most system fonts do not draw these signs yet. The storefront themes and the dashboard declare
this font with `unicode-range: U+20C1, U+20C3`, so a browser downloads it only for a page that shows
one of the signs. Do not use U+FDFC (RIAL SIGN) for the riyal. Unicode says it must not be reused.

## Sources

The files in `sources/` are the central banks' downloads, unchanged.

`sources/saudi-riyal-sign.svg`
- SAMA, "Saudi Riyal Symbol Guidelines", section "Symbol Design Download", SVG for
  "Digital vector graphics".
- Page: https://www.sama.gov.sa/en-US/Currency/SRS/Pages/Guideline.aspx
- File: https://www.sama.gov.sa/ar-sa/Currency/Documents/Saudi_Riyal_Symbol-2.svg
- sama.gov.sa refused connections from our build server, so the file came from the Internet
  Archive's copies of that URL. Copies from 2025-02-20, 2026-01-23 and 2026-06-05 are identical:
  https://web.archive.org/web/20260605000317id_/https://www.sama.gov.sa/ar-sa/Currency/Documents/Saudi_Riyal_Symbol-2.svg
- SHA-256: `dc035ad6d18c543a79d7e2f24458ab17b869c030875dc2f1d18f2fa9dda9e404`

`sources/uae-dirham-sign.svg`
- CBUAE, "Dirham Currency Symbol Guideline", version 1.0, page 29 "Downloads", SVG for
  "Digital vector graphics". The zip holds one file, `Dirham Currency Symbol - Black.svg`.
- Guideline: https://www.centralbank.ae/media/jlhi41xu/dirham_currency_symbol_guideline_english.pdf
- File: https://centralbank.ae/media/ryxjtjnr/dirham-currency-symbol-svg.zip
- SHA-256: `6a058fc563d06a65c78abf5aa6d95c415990ab43a359ec7c72fd6eb6e2df5b8d`

## Terms of use

Neither bank attaches a licence (such as CC or OFL) to the artwork. Both publish it for anyone to
download and ask for it to be used in prices:

- SAMA's guideline offers the symbol as EPS ("high quality printing"), PNG ("general use") and
  SVG ("digital vector graphics"). It lists "applications and e-commerce stores" and "price tags
  on products" among the places the symbol is used.
- The CBUAE guideline says the symbol "has now been developed and must be used hereafter". Its
  use cases include "online shopping and in-store, on pricing labels" and "financial apps". It
  allows the symbol to "be adapted to match different font styles and weights" if the shape stays
  the same. It must not be used as a logo, on splash screens, or together with "AED".

This font follows the rules of both guidelines. The sign goes to the left of the amount, with a
space, and to the left of a minus sign. Its height matches the numerals. Commera uses the signs
only next to prices, never as branding. The glyphs are not copied from any other font.

## Build

```
UV_CACHE_DIR=<a cache dir on a disk with room> \
  uvx --with "fonttools[woff]==4.55.0" python commera/public/fonts/currency-signs/build.py
```

`build.py` scales each SVG so that the sign is 0.7 em high on the baseline, with a 0.06 em side
bearing. The output is reproducible: the same sources give the same bytes.
