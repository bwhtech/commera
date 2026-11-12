"""Build currency-signs.woff2 from the central banks' artwork in sources/. README.md has the command."""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import SVGPath

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "currency-signs.woff2"
FAMILY = "Commera Currency Signs"
VERSION = "1.000"

UNITS_PER_EM = 1000
# Both guides ask for the sign at the height of the numerals, about 0.7 em in the theme fonts.
SIGN_HEIGHT = 700
SIDE_BEARING = 60
ASCENT, DESCENT = 800, -200
# A fixed date keeps the build reproducible: 2026-11-12, in seconds since 1904-01-01.
TIMESTAMP = 3845923200

SIGNS = {
	"uni20C1": (0x20C1, "saudi-riyal-sign.svg"),
	"uni20C3": (0x20C3, "uae-dirham-sign.svg"),
}


def main():
	glyphs = {".notdef": (TTGlyphPen(None).glyph(), 500)}
	for name, (_, source) in SIGNS.items():
		glyphs[name] = draw_sign(HERE / "sources" / source)
	write_font(glyphs)
	print(f"Wrote {OUTPUT.relative_to(HERE.parents[3])} ({OUTPUT.stat().st_size} bytes)")


def draw_sign(source: Path):
	"""Fit the artwork on the baseline at SIGN_HEIGHT, as a TrueType glyph and its advance width."""
	outline = RecordingPen()
	# SVG's y axis points down and a font's points up.
	SVGPath(str(source), transform=(1, 0, 0, -1, 0, 0)).draw(outline)
	x_min, y_min, x_max, y_max = get_bounds(outline)
	scale = SIGN_HEIGHT / (y_max - y_min)
	placement = (scale, 0, 0, scale, SIDE_BEARING - x_min * scale, -y_min * scale)

	glyph_pen = TTGlyphPen(None)
	# TrueType wants outer contours clockwise; the flip turned the artwork's around.
	reverse = get_area(outline) > 0
	outline.replay(TransformPen(Cu2QuPen(glyph_pen, max_err=0.5, reverse_direction=reverse), placement))
	advance = round((x_max - x_min) * scale) + 2 * SIDE_BEARING
	return glyph_pen.glyph(), advance


def get_bounds(outline: RecordingPen):
	pen = BoundsPen(None)
	outline.replay(pen)
	return pen.bounds


def get_area(outline: RecordingPen) -> float:
	pen = AreaPen()
	outline.replay(pen)
	return pen.value


def get_left_side_bearing(glyph) -> int:
	glyph.recalcBounds(None)
	return getattr(glyph, "xMin", 0)


def write_font(glyphs: dict):
	builder = FontBuilder(UNITS_PER_EM, isTTF=True)
	builder.font.recalcTimestamp = False
	builder.setupGlyphOrder(list(glyphs))
	builder.setupCharacterMap({codepoint: name for name, (codepoint, _) in SIGNS.items()})
	builder.setupGlyf({name: glyph for name, (glyph, _) in glyphs.items()})
	builder.setupHorizontalMetrics(
		{name: (advance, get_left_side_bearing(glyph)) for name, (glyph, advance) in glyphs.items()}
	)
	builder.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
	builder.setupNameTable(
		{
			"familyName": FAMILY,
			"styleName": "Regular",
			"uniqueFontIdentifier": f"{FAMILY} {VERSION}",
			"fullName": FAMILY,
			"psName": FAMILY.replace(" ", ""),
			"version": f"Version {VERSION}",
			"description": "U+20C1 SAUDI RIYAL SIGN and U+20C3 UAE DIRHAM SIGN, drawn from the official "
			"artwork of the Saudi Central Bank (SAMA) and the Central Bank of the UAE. See README.md.",
		}
	)
	builder.setupOS2(
		version=4,
		sTypoAscender=ASCENT,
		sTypoDescender=DESCENT,
		sTypoLineGap=0,
		usWinAscent=ASCENT,
		usWinDescent=-DESCENT,
		sxHeight=500,
		sCapHeight=SIGN_HEIGHT,
		fsType=0,
		fsSelection=0x40 | 0x80,  # Regular, and use the typo metrics.
		achVendID="NONE",
	)
	builder.setupPost()
	builder.setupHead(
		unitsPerEm=UNITS_PER_EM, fontRevision=float(VERSION), created=TIMESTAMP, modified=TIMESTAMP
	)
	builder.font.flavor = "woff2"
	builder.save(OUTPUT)


if __name__ == "__main__":
	main()
