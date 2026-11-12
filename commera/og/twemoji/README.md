# Twemoji for OG cards

`twemoji.json.br` holds the emoji graphics that OG cards draw. It is the `assets/svg` folder of
[Twemoji](https://github.com/jdecked/twemoji) v17.0.3, packed into one brotli-compressed JSON object.
Each key is a Twemoji file name without `.svg`, and each value is that file's SVG text.

## Attribution

Emoji graphics: Twemoji, copyright 2014–2021 Twitter and 2022–present Jason Sofonia, Justine De Caires
and the Twemoji contributors. Licensed under CC-BY 4.0 (see `LICENSE-GRAPHICS`,
<https://creativecommons.org/licenses/by/4.0/>).

Changes: the SVG files are packed into one compressed file. The graphics themselves are unchanged.

## Rebuild

Download a Twemoji release, then run from the app root:

```
node scripts/build_twemoji_pack.mjs <twemoji>/assets/svg commera/og/twemoji/twemoji.json.br
```
