"""Assemble the static mockup pages from src/ into dist/."""

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
PHOTO_TONES = json.loads((SRC / "photo-tones.json").read_text())

ICONS = {
	"search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/>',
	"user": '<circle cx="12" cy="8" r="3.75"/><path d="M4.75 20c.6-3.6 3.6-6 7.25-6s6.65 2.4 7.25 6"/>',
	"bag": '<path d="M4.75 7.75h14.5v12.5H4.75z"/><path d="M8.75 10V6.75a3.25 3.25 0 016.5 0V10"/>',
	"heart": '<path d="M12 19.5s-7.25-4.3-7.25-9.6A3.9 3.9 0 0112 7.6a3.9 3.9 0 017.25 2.3c0 5.3-7.25 9.6-7.25 9.6z"/>',
	"menu": '<path d="M4 7.5h16M4 12h16M4 16.5h10"/>',
	"x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
	"chev-down": '<path d="M7 10l5 5 5-5"/>',
	"chev-right": '<path d="M10 7l5 5-5 5"/>',
	"chev-left": '<path d="M14 7l-5 5 5 5"/>',
	"arrow": '<path d="M4.5 12h14.5M14 7l5 5-5 5"/>',
	"minus": '<path d="M6 12h12"/>',
	"plus": '<path d="M12 6v12M6 12h12"/>',
	"truck": '<path d="M3.75 6.75h10.5v9.5H3.75zM14.25 10.25h3.5l2.5 3v3h-6"/><circle cx="7.5" cy="17.5" r="1.6"/><circle cx="17" cy="17.5" r="1.6"/>',
	"return": '<path d="M8.5 5.5L4.75 9.25 8.5 13"/><path d="M4.75 9.25h9.5a5 5 0 010 10h-4"/>',
	"shield": '<path d="M12 3.75l7 2.75v5.25c0 4.2-3 7.4-7 8.5-4-1.1-7-4.3-7-8.5V6.5z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
	"sparkle": '<path d="M12 4v4M12 16v4M4 12h4M16 12h4M6.6 6.6l2.2 2.2M15.2 15.2l2.2 2.2M6.6 17.4l2.2-2.2M15.2 8.8l2.2-2.2"/>',
	"sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><path d="M13 4.75v4.5h4v-4.5zM7 14.75v4.5h4v-4.5z"/>',
	"zoom": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4M11 8.25v5.5M8.25 11h5.5"/>',
	"tag": '<path d="M4.75 4.75h7l7.5 7.5-7 7-7.5-7.5z"/><circle cx="8.75" cy="8.75" r="1.1"/>',
	"lock": '<path d="M5.75 10.75h12.5v9.5H5.75z"/><path d="M8.75 10.75V7.5a3.25 3.25 0 016.5 0v3.25"/>',
	"star": '<path d="M12 4.2l2.35 4.9 5.35.65-3.95 3.7 1 5.3L12 16.15 7.25 18.75l1-5.3-3.95-3.7 5.35-.65z" fill="currentColor" stroke="none"/>',
	"check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
}

COLOURS = {
	"mint": "#a3d8c2",
	"tomato": "#e04a2b",
	"butter": "#ecd5a6",
	"black": "#25241f",
	"white": "#f4f3ef",
	"jade": "#6ec4a6",
	"saffron": "#e8c13a",
	"delft": "#3f5fa8",
	"sky": "#a9d5df",
	"sage": "#b8cbb2",
	"tangerine": "#e8743a",
	"sand": "#e3c9a0",
	"seafoam": "#8fd3c4",
	"ivory": "#efe8d6",
	"apricot": "#e9a86a",
	"speckle": "#d9d8d3",
}

PRODUCTS = {
	"casserole-mint": ("Lidded casserole", "Mint · 3.5 L", 84, 98, ["mint", "tomato", "butter"], None),
	"casserole-tomato": ("Lidded casserole", "Tomato · 3.5 L", 84, None, ["tomato", "mint", "butter"], None),
	"saucepan-butter": ("Pouring saucepan", "Butter · 1.2 L", 48, 60, ["butter", "ivory", "sage"], "Sale"),
	"coffee-pot-white": ("Coffee pot", "White · 1 L", 62, None, ["white", "sand"], "New"),
	"cup-jade": ("Camp cup", "Jade · 300 ml", 18, None, ["jade", "seafoam", "sky"], None),
	"gratin-pan-saffron": (
		"Gratin pan",
		"Saffron · 28 cm",
		56,
		None,
		["saffron", "apricot", "tangerine"],
		None,
	),
	"jug-delft": ("Water jug", "Delft · 1.8 L", 72, None, ["delft", "white"], "Last one"),
	"colander-mint": ("Footed colander", "Mint · 24 cm", 44, None, ["mint"], None),
	"bowl-white-2": ("Wash bowl", "White · 32 cm", 38, None, ["white"], None),
	"funnel-mint": ("Kitchen funnel", "Mint", 16, None, ["mint", "speckle", "white"], None),
	"butter-dish-mint": ("Butter dish", "Mint", 46, None, ["mint"], "New"),
	"utensil-rack-mint": ("Utensil rack", "Mint", 58, None, ["mint", "delft"], None),
	"casserole-black": ("Stock pot", "Black · 5 L", 96, 120, ["black"], "Sale"),
	"casserole-butter": ("Lidded casserole", "Butter · 3.5 L", 84, None, ["butter", "mint", "tomato"], None),
	"saucepan-ivory": ("Pouring saucepan", "Ivory · 1.2 L", 48, None, ["ivory", "butter", "sage"], None),
	"gratin-pan-apricot": (
		"Gratin pan",
		"Apricot · 28 cm",
		56,
		None,
		["apricot", "saffron", "tangerine"],
		None,
	),
	"cup-seafoam": ("Camp cup", "Seafoam · 300 ml", 18, None, ["seafoam", "jade"], None),
	"jug-white": ("Water jug", "White · 1.8 L", 68, None, ["white", "delft"], None),
	"funnel-speckle": ("Kitchen funnel", "Speckle", 16, None, ["speckle", "mint", "white"], None),
	"funnel-white": ("Kitchen funnel", "White", 16, None, ["white", "mint", "speckle"], None),
	"utensil-rack-delft": ("Utensil rack", "Delft", 58, None, ["delft", "mint"], None),
	"cup-sky": ("Breakfast cup", "Sky · 450 ml", 22, None, ["sky", "seafoam", "jade"], None),
	"saucepan-sage": ("Pouring saucepan", "Sage · 1.2 L", 48, None, ["sage", "butter", "ivory"], None),
	"gratin-pan-tangerine": (
		"Gratin pan",
		"Tangerine · 28 cm",
		56,
		None,
		["tangerine", "saffron", "apricot"],
		None,
	),
	"coffee-pot-sand": ("Coffee pot", "Sand · 1 L", 62, None, ["sand", "white"], None),
	"candle-holder-mint": ("Chamber candle holder", "Mint", 34, None, ["mint"], None),
}


CATEGORIES = {
	"casserole": "Cookware",
	"saucepan": "Cookware",
	"gratin-pan": "Cookware",
	"colander": "Cookware",
	"cup": "Tableware",
	"bowl": "Tableware",
	"butter-dish": "Tableware",
	"jug": "Tableware",
	"coffee-pot": "Coffee & tea",
	"funnel": "Kitchen tools",
	"utensil-rack": "Kitchen tools",
	"candle-holder": "Home",
}

COLLECTIONS = [
	("Cookware", "category"),
	("Tableware", "category"),
	("Coffee & tea", "category"),
	("Kitchen tools", "category"),
	("Sale", "sale"),
	*[(name.title(), "colour") for name in ("mint", "tomato", "butter", "delft", "white")],
]


def category(slug):
	return next(name for prefix, name in CATEGORIES.items() if slug.startswith(prefix))


def search_index():
	products = []
	for slug, (title, meta, price, compare, colours, badge) in PRODUCTS.items():
		terms = " ".join([title, meta, category(slug), "sale" if compare else ""])
		products.append(
			{
				"slug": slug,
				"title": title,
				"meta": meta,
				"category": category(slug),
				"terms": terms.lower(),
				"price": price_html(price, compare),
				"amount": price,
				"compare": compare,
				"colour": meta.split(" · ")[0],
				"colours": colours,
				"badge": badge,
				"background": PHOTO_TONES[slug],
				"card": card(slug),
			}
		)
	collections = []
	for name, kind in COLLECTIONS:
		matches = [
			item
			for item in products
			if (
				item["category"] == name
				if kind == "category"
				else bool(item["compare"])
				if kind == "sale"
				else item["colour"].lower() == name.lower()
			)
		]
		collections.append({"title": name, "count": len(matches)})
	return (
		"window.CATALOG = "
		+ json.dumps(
			{
				"products": products,
				"collections": collections,
				"colours": COLOURS,
				"icons": {name: icon(name, "icon-sm") for name in ("minus", "plus")},
			}
		)
		+ ";\n"
	)


def icon(name, extra=""):
	return f'<svg class="icon {extra}" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def price_html(price, compare):
	if compare:
		return f'<s>${compare}</s><span class="sale">${price}</span>'
	return f"${price}"


def card(slug):
	title, meta, price, compare, colours, badge = PRODUCTS[slug]
	badge_class = {"Sale": "badge badge-sale", "Last one": "badge badge-dark"}.get(badge, "badge")
	badge_html = f'<span class="{badge_class}">{badge}</span>' if badge else ""
	dots = "".join(f'<i style="background:{COLOURS[c]}"></i>' for c in colours[:4])
	return f"""<article class="card" data-product="{slug}">
	<div class="card-media" style="background:{PHOTO_TONES[slug]}">
		<img src="img/{slug}.jpg" loading="lazy" width="900" height="675" alt="{title}, {meta.split(' · ')[0]}">
		{badge_html}
		<span class="card-view" aria-hidden="true">View piece {icon("arrow", "icon-sm")}</span>
	</div>
	<div class="card-body">
		<h3 class="card-title"><a href="product.html?item={slug}">{title}</a></h3>
		<p class="card-price">{price_html(price, compare)}</p>
		<p class="card-meta">{meta}</p>
		<div class="dots" aria-hidden="true">{dots}</div>
	</div>
</article>"""


def collection_count(name):
	return sum(1 for slug in PRODUCTS if category(slug) == name)


def render(text, partials):
	text = re.sub(r"\{\{count:([^}]+)\}\}", lambda m: str(collection_count(m[1])), text)
	text = re.sub(r"\{\{colour:([^}]+)\}\}", lambda m: COLOURS[m[1]], text)
	text = re.sub(r"\{\{photo:([^}]+)\}\}", lambda m: PHOTO_TONES[m[1]], text)
	text = re.sub(
		r"<!--@cards:([\w,\-]+)-->", lambda m: "\n".join(card(s) for s in m.group(1).split(",")), text
	)
	text = re.sub(r"<!--@(\w+)-->", lambda m: render(partials[m.group(1)], partials), text)
	text = re.sub(r"\{icon:([\w\-]+)(?: ([\w\-]+))?\}", lambda m: icon(m.group(1), m.group(2) or ""), text)
	return text


def version_assets(html):
	def version(match):
		name = match[2]
		digest = hashlib.sha256((DIST / name).read_bytes()).hexdigest()[:10]
		return f'{match[1]}="{name}?v={digest}"'

	return re.sub(r'(href|src)="([\w.-]+\.(?:css|js))"', version, html)


def inline(html):
	css = "".join((DIST / name).read_text() for name in ("styles.css", "pages.css", "search.css"))
	for font in (DIST / "fonts").iterdir():
		data = base64.b64encode(font.read_bytes()).decode()
		css = css.replace(f"fonts/{font.name}", f"data:font/woff2;base64,{data}")
	html = re.sub(r'<link rel="stylesheet"[^>]*>\s*', "", html)
	html = html.replace("<head>", '<head>\n<base href="../">', 1)
	html = html.replace("</head>", f"<style>{css}</style>\n</head>", 1)
	html = re.sub(
		r'<script src="([\w.-]+\.js)(?:\?v=[\w]+)?"></script>',
		lambda m: "<script>" + (DIST / m[1]).read_text() + "</script>",
		html,
	)
	return html.replace('src="img/', f'src="{DIST}/img/')


def main():
	DIST.mkdir(exist_ok=True)
	(DIST / "inline").mkdir(exist_ok=True)
	for folder in ("fonts", "img"):
		shutil.copytree(ROOT / folder, DIST / folder, dirs_exist_ok=True)
	for name in (
		"styles.css",
		"pages.css",
		"search.css",
		"store.js",
		"collection.js",
		"product.js",
		"cart.js",
		"search.js",
	):
		shutil.copy(SRC / name, DIST / name)
	(DIST / "catalog.js").write_text(search_index())
	partials = {p.stem: p.read_text() for p in (SRC / "partials").glob("*.html")}
	for page in SRC.glob("*.html"):
		html = version_assets(render(page.read_text(), partials))
		(DIST / page.name).write_text(html)
		(DIST / "inline" / page.name).write_text(inline(html))
		print(page.name)


if __name__ == "__main__":
	main()
