// Satori shapes each run with HarfBuzz, but it places words left to right and ignores `direction`.
// Before Satori runs, this puts right-to-left text into words in visual order and, on a
// right-to-left card, mirrors the layout.

import { isColumn, mirrorStyle } from './og_mirror.mjs';

export const ARABIC_FONT = 'IBM Plex Sans Arabic';
export const HEBREW_FONT = 'IBM Plex Sans Hebrew';

const RTL_CHAR = /[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]/;
const HEBREW_CHAR = /[\u0590-\u05FF\uFB1D-\uFB4F]/;
const LETTER = /\p{L}/u;
const DIGIT = /\p{Nd}/u;
// Leading punctuation, the word, trailing punctuation: "(مقاس" is "(" and "مقاس".
const WORD_PARTS = /^([^\p{L}\p{N}]*)(.*?)([^\p{L}\p{N}]*)$/su;
// Open Sans and IBM Plex both draw a space about a quarter of an em wide.
const WORD_GAP = '0.26em';
const MIRRORED = {
	'(': ')',
	')': '(',
	'[': ']',
	']': '[',
	'{': '}',
	'}': '{',
	'<': '>',
	'>': '<',
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
		if (this.rtl) {
			mirrorStyle(style, context);
		}
		const childContext = {
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
		this.rtl = rtl;
		this.context = context;
		this.tokens = tokenize(text);
		resolveDirections(this.tokens, rtl);
	}

	render() {
		const pieces = groupRuns(this.tokens).flatMap((run) => {
			if (run.rtl === this.rtl) {
				return run.tokens.map((token) => ({
					node: this.tokenNode(token),
					space: token.space,
				}));
			}
			const node = run.rtl
				? this.rightToLeftRun(run.tokens)
				: this.leftToRightRun(run.tokens);
			return [{ node, space: run.tokens.at(-1).space }];
		});
		const words = joinWords(pieces).map(({ nodes, space }) =>
			withGap(
				nodes.length > 1 ? row(nodes, this.rtl, {}) : nodes[0],
				space,
				this.rtl,
			),
		);
		const justifyContent = justifyFor(this.context.textAlign, this.rtl);
		return row(words, this.rtl, { flexWrap: 'wrap', justifyContent });
	}

	leftToRightRun(tokens) {
		// One text node, so Satori wraps a long Latin run by itself.
		const last = tokens.length - 1;
		const text = tokens
			.map(
				(token, index) => token.text + (token.space && index < last ? ' ' : ''),
			)
			.join('');
		return { type: 'div', props: { style: {}, children: text } };
	}

	rightToLeftRun(tokens) {
		const last = tokens.length - 1;
		const items = tokens.map((token, index) =>
			withGap(this.tokenNode(token), token.space && index < last, true),
		);
		return row(items, true, {});
	}

	tokenNode(token) {
		const style = {};
		if (hasRtlText(token.text)) {
			const font = HEBREW_CHAR.test(token.text) ? HEBREW_FONT : ARABIC_FONT;
			const inherited = this.context.fontFamily;
			style.fontFamily = inherited ? `'${font}', ${inherited}` : `'${font}'`;
		}
		// HarfBuzz reads Arabic-Indic digits as right-to-left text, so each digit is placed on its own.
		if (token.type === 'EN' && hasRtlText(token.text)) {
			const digits = [...token.text].map((digit) => ({
				type: 'div',
				props: { style: {}, children: digit },
			}));
			return row(digits, false, style);
		}
		// HarfBuzz shapes a lone bracket left to right, so a right-to-left one is mirrored here.
		const text =
			token.rtl && token.type === 'N'
				? [...token.text].map((c) => MIRRORED[c] ?? c).join('')
				: token.text;
		return { type: 'div', props: { style, children: text } };
	}
}

/** Pieces with no space between them, such as a word and its brackets, wrap as one. */
function joinWords(pieces) {
	const words = [];
	let word = null;
	for (const piece of pieces) {
		if (!word) {
			word = { nodes: [], space: false };
			words.push(word);
		}
		word.nodes.push(piece.node);
		word.space = piece.space;
		if (piece.space) {
			word = null;
		}
	}
	return words;
}

function tokenize(text) {
	const tokens = [];
	for (const word of text.trim().split(/\s+/)) {
		// Each punctuation mark takes its own place: ")." reads "(." in right-to-left order.
		const [, leading, core, trailing] = WORD_PARTS.exec(word);
		const parts = [...leading, core, ...trailing].filter(Boolean);
		tokens.push(
			...parts.map((part) => ({
				text: part,
				type: bidiType(part),
				space: false,
			})),
		);
		tokens.at(-1).space = true;
	}
	tokens.at(-1).space = false;
	return tokens;
}

function bidiType(text) {
	for (const char of text) {
		if (LETTER.test(char)) {
			return RTL_CHAR.test(char) ? 'R' : 'L';
		}
	}
	return DIGIT.test(text) ? 'EN' : 'N';
}

/** Sets `token.rtl`: Unicode's bidi rules W7, N1 and N2, applied to whole words. */
function resolveDirections(tokens, paragraphRtl) {
	let previousStrong = null;
	for (const token of tokens) {
		if (token.type === 'R' || token.type === 'L') {
			previousStrong = token.type;
			token.rtl = token.type === 'R';
		} else if (token.type === 'EN') {
			// A number after left-to-right text joins it; otherwise it sits in the right-to-left order.
			token.rtl = previousStrong ? previousStrong === 'R' : paragraphRtl;
		}
	}
	for (const [index, token] of tokens.entries()) {
		if (token.type !== 'N') {
			continue;
		}
		const before =
			tokens.slice(0, index).findLast((other) => other.type !== 'N')?.rtl ??
			paragraphRtl;
		const after =
			tokens.slice(index + 1).find((other) => other.type !== 'N')?.rtl ??
			paragraphRtl;
		token.rtl = before === after ? before : paragraphRtl;
	}
}

function groupRuns(tokens) {
	const runs = [];
	for (const token of tokens) {
		const last = runs.at(-1);
		if (last && last.rtl === token.rtl) {
			last.tokens.push(token);
		} else {
			runs.push({ rtl: token.rtl, tokens: [token] });
		}
	}
	return runs;
}

function row(children, rtl, style) {
	const flexDirection = rtl ? 'row-reverse' : 'row';
	return {
		type: 'div',
		props: { style: { display: 'flex', flexDirection, ...style }, children },
	};
}

function withGap(item, space, rtlRow) {
	// The gap goes after the word in reading order: on its left in a right-to-left row.
	if (space) {
		item.props.style[rtlRow ? 'marginLeft' : 'marginRight'] = WORD_GAP;
	}
	return item;
}

function justifyFor(textAlign, rtl) {
	if (textAlign === 'center') {
		return 'center';
	}
	const towardRight = textAlign === 'right' || textAlign === 'end';
	return towardRight === rtl ? 'flex-start' : 'flex-end';
}
