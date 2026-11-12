// Glyphs the bundled fonts do not have: emoji come from the bundled Twemoji pack,
// and other astral characters get a compatibility form or are left out, never a box.

import { readFileSync } from 'node:fs';
import { brotliDecompressSync } from 'node:zlib';

const PACK = new URL('./twemoji/twemoji.json.br', import.meta.url);
const EMOJI = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u20e3]/u;
// Shown as emoji even where a font has the base character, as in the keycap 1️⃣.
const EMOJI_PRESENTATION =
	/[\p{Emoji_Presentation}\p{Emoji_Modifier}\p{Regional_Indicator}\ufe0f\u20e3\u200d\u{e0020}-\u{e007f}]/u;
const ASTRAL = /[\u{10000}-\u{10ffff}]/u;
const DROPPED = '\0';
const graphemes = new Intl.Segmenter('und', { granularity: 'grapheme' });
let pack;

/** Satori's `graphemeImages`: the emoji in the tree's text as Twemoji images. */
export function graphemeImages(tree) {
	const images = {};
	for (const text of texts(tree)) {
		if (!EMOJI_PRESENTATION.test(text)) continue;
		for (const { segment } of graphemes.segment(text)) {
			const image = EMOJI_PRESENTATION.test(segment) && emojiImage(segment);
			if (image) images[segment] = image;
		}
	}
	return images;
}

/** Satori's `loadAdditionalAsset`, for text-style pictographs such as ❤ that no font has. */
export async function loadAdditionalAsset(code, segment) {
	return code === 'emoji' ? emojiImage(segment) : undefined;
}

/** The Twemoji file name for one grapheme, or undefined when it is not an emoji. */
export function emojiKey(grapheme) {
	pack ??= JSON.parse(brotliDecompressSync(readFileSync(PACK)));
	return emojiKeys(grapheme).find((candidate) => pack[candidate]);
}

/** `tree` with every text node passed through `renderableText`. */
export function withRenderableText(node) {
	if (typeof node === 'string') return renderableText(node);
	if (Array.isArray(node)) return node.map(withRenderableText);
	if (!node?.props) return node;
	const children = withRenderableText(node.props.children);
	return { ...node, props: { ...node.props, children } };
}

/** No bundled font draws an astral character, so use its NFKC form or leave it out. */
export function renderableText(text) {
	if (!ASTRAL.test(text)) return text;
	let output = '';
	for (const { segment } of graphemes.segment(text)) {
		output += renderableGrapheme(segment);
	}
	return output.replace(/[\s\0]*\0[\s\0]*/g, joinGap);
}

function emojiImage(grapheme) {
	const key = emojiKey(grapheme);
	return (
		key &&
		`data:image/svg+xml;base64,${Buffer.from(pack[key]).toString('base64')}`
	);
}

function emojiKeys(grapheme) {
	const points = [...grapheme].map((char) => char.codePointAt(0).toString(16));
	const bare = points.filter((point) => point !== 'fe0f');
	// Twemoji keeps U+FE0F only in some ZWJ names; a sequence newer than the pack shows its base.
	return [points.join('-'), bare.join('-'), bare[0]];
}

function* texts(node) {
	if (typeof node === 'string') {
		yield node;
	} else if (Array.isArray(node)) {
		for (const child of node) yield* texts(child);
	} else if (node?.props) {
		yield* texts(node.props.children);
	}
}

/** A dropped word between two spaces leaves one space. */
function joinGap(run) {
	return /^\s/.test(run) && /\s$/.test(run)
		? run[0]
		: run.replaceAll(DROPPED, '');
}

function renderableGrapheme(grapheme) {
	if (!ASTRAL.test(grapheme) || EMOJI.test(grapheme)) return grapheme;
	// Mathematical bold letters such as 𝐒𝐀𝐋𝐄 read as SALE.
	const compatible = grapheme.normalize('NFKC');
	return (
		[...compatible].filter((char) => !ASTRAL.test(char)).join('') || DROPPED
	);
}
