// Satori shapes logical runs with HarfBuzz but ignores paragraph direction.
// Resolve visual run order and mirror right-to-left layouts before rendering.

import assert from 'node:assert/strict';
import bidiFactory from 'bidi-js';
import { isColumn, mirrorStyle } from './og_mirror.mjs';

export const ARABIC_FONT = 'IBM Plex Sans Arabic';
export const HEBREW_FONT = 'IBM Plex Sans Hebrew';

const RTL_CHAR = /[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]/;
const HEBREW_CHAR = /[\u0590-\u05FF\uFB1D-\uFB4F]/;
const WORD_GAP = '0.26em';
const bidi = bidiFactory();
const graphemes = new Intl.Segmenter('und', { granularity: 'grapheme' });
const placeholders = {
	L: 'A',
	R: 'א',
	AL: 'ا',
	EN: '0',
	ES: '+',
	ET: '#',
	CS: ',',
	B: '\u2029',
	S: '\t',
	WS: ' ',
	AN: '٠',
	ON: '\ufffc',
	NSM: '\u0300',
	BN: '\u200b',
	LRE: '\u202a',
	RLE: '\u202b',
	PDF: '\u202c',
	LRO: '\u202d',
	RLO: '\u202e',
	LRI: '\u2066',
	RLI: '\u2067',
	FSI: '\u2068',
	PDI: '\u2069',
};

export function hasRtlText(text) {
	return RTL_CHAR.test(text);
}

/** `tree` is satori-html's output. `direction` is the card's language direction. */
export function prepareTree(tree, direction) {
	if (direction !== 'rtl') {
		return new BidiTree(false).visit(tree, {});
	}
	// Satori reads `start` as left, so a right-to-left card starts out right-aligned.
	const prepared = new BidiTree(true).visit(tree, { textAlign: 'right' });
	prepared.props.style.textAlign ??= 'right';
	return prepared;
}

class BidiTree {
	constructor(rtl) {
		this.rtl = rtl;
	}

	visit(node, context) {
		if (typeof node === 'string') {
			return hasRtlText(node)
				? new Paragraph(node, this.rtl, context).render()
				: node;
		}
		if (Array.isArray(node)) {
			return node.map((child) => this.visit(child, context));
		}
		if (!node?.props) {
			return node;
		}

		const style = { ...(node.props.style || {}) };
		const noMirror =
			context.noMirror ||
			node.props['data-og-no-mirror'] !== undefined ||
			style.flexDirection === 'row-reverse' ||
			style.textAlign === 'right' ||
			style.direction === 'rtl';
		if (this.rtl && !noMirror) {
			mirrorStyle(style, context);
		}
		const childContext = {
			noMirror,
			textAlign: style.textAlign ?? context.textAlign,
			fontFamily: style.fontFamily ?? context.fontFamily,
			inColumn: isColumn(style),
			alignItems: style.alignItems,
		};
		const children = this.visit(node.props.children, childContext);
		if (
			typeof children !== 'string' &&
			typeof node.props.children === 'string'
		) {
			// Satori wants an explicit flex display on a div whose child is an element.
			style.display ??= 'flex';
		}
		return { ...node, props: { ...node.props, style, children } };
	}
}

/** One text node as a wrapping row of words, each run in its own direction. */
class Paragraph {
	constructor(text, rtl, context) {
		this.text = text;
		this.rtl = rtl;
		this.context = context;
	}

	render() {
		const pieces = visualRuns(this.text, this.rtl).map(({ text, level }) => {
			const style = {};
			if (hasRtlText(text)) {
				const font = HEBREW_CHAR.test(text) ? HEBREW_FONT : ARABIC_FONT;
				style.fontFamily = `'${font}', ${
					this.context.fontFamily || 'OpenSans'
				}`;
			}
			if (/^\s+$/.test(text)) {
				return {
					type: 'div',
					props: { style: { width: WORD_GAP }, children: '' },
				};
			}
			// HarfBuzz reverses Arabic-script digits even in an even-level run.
			const children =
				/[\u0660-\u0669\u06f0-\u06f9]/.test(text) && !(level & 1)
					? text
							.match(
								/[\u0660-\u0669\u06f0-\u06f9]|[^\u0660-\u0669\u06f0-\u06f9]+/g,
							)
							.map((char) => ({ type: 'div', props: { children: char } }))
					: text;
			if (Array.isArray(children)) Object.assign(style, { display: 'flex' });
			return { type: 'div', props: { style, children } };
		});
		return row(pieces, false, {
			flexWrap: 'wrap',
			justifyContent:
				this.context.textAlign === 'center'
					? 'center'
					: this.rtl
					  ? 'flex-end'
					  : 'flex-start',
		});
	}
}

/** UAX #9 levels and L1/L2 reordering precede grouping for HarfBuzz shaping. */
export function visualRuns(text, rtl) {
	const units = bidiUnits(text);
	const input = units.map(({ placeholder }) => placeholder).join('');
	assert.equal(
		input.length,
		units.length,
		'Each bidi unit must have one placeholder',
	);
	const embedding = bidi.getEmbeddingLevels(input, rtl ? 'rtl' : 'ltr');
	const indices = bidi.getReorderedIndices(input, embedding);
	const mirrors = bidi.getMirroredCharactersMap(input, embedding.levels);
	const runs = [];
	for (const index of indices) {
		const char = units[index].text;
		if (/[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/.test(char)) continue;
		const level = embedding.levels[index];
		const last = runs.at(-1);
		const step = level & 1 ? -1 : 1;
		const space = /\s/.test(char);
		const bracket = bidi.getMirroredCharacter(char);
		if (
			last &&
			last.level === level &&
			index === last.index + step &&
			(!(level & 1) ||
				(!bracket && !last.bracket && space === last.space && !space))
		) {
			last.text = level & 1 ? char + last.text : last.text + char;
			last.index = index;
		} else {
			runs.push({
				text: mirrors.get(index) || char,
				level,
				index,
				space,
				bracket,
			});
		}
	}
	return runs;
}

function bidiUnits(text) {
	const units = [];
	for (const { segment } of graphemes.segment(text)) {
		// Keep emoji selectors, modifiers and joiners attached during L2 reordering.
		if (
			/[\p{Extended_Pictographic}\p{Regional_Indicator}\u20e3]/u.test(segment)
		) {
			units.push({
				text: segment,
				placeholder: placeholders[bidi.getBidiCharTypeName(segment)],
			});
			continue;
		}
		for (const char of segment) {
			// bidi-js classifies code units internally; its public lookup accepts code points.
			const placeholder =
				char.length === 2 ? placeholders[bidi.getBidiCharTypeName(char)] : char;
			if (!placeholder) throw new Error('Unsupported astral bidi class');
			units.push({ text: char, placeholder });
		}
	}
	return units;
}

function row(children, rtl, style) {
	const flexDirection = rtl ? 'row-reverse' : 'row';
	return {
		type: 'div',
		props: { style: { display: 'flex', flexDirection, ...style }, children },
	};
}
