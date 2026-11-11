// Satori runs Yoga left to right only, so a right-to-left card flips its own layout styles.

const SIDE_PAIRS = [
	['marginLeft', 'marginRight'],
	['paddingLeft', 'paddingRight'],
	['left', 'right'],
	['borderLeft', 'borderRight'],
	['borderLeftWidth', 'borderRightWidth'],
	['borderLeftColor', 'borderRightColor'],
	['borderLeftStyle', 'borderRightStyle'],
	['borderTopLeftRadius', 'borderTopRightRadius'],
	['borderBottomLeftRadius', 'borderBottomRightRadius'],
];
const BOX_SHORTHANDS = [
	'margin',
	'padding',
	'borderWidth',
	'borderColor',
	'borderStyle',
];
const OPPOSITE = {
	left: 'right',
	right: 'left',
	start: 'end',
	end: 'start',
	'flex-start': 'flex-end',
	'flex-end': 'flex-start',
};

export function mirrorStyle(style, context) {
	const column = isColumn(style);
	if (typeof style.transform === 'string') {
		style.transform = style.transform.replace(
			/translateX\(\s*(-?[\d.]+)([^)]*)\)/g,
			(_match, amount, unit) => `translateX(${-Number(amount)}${unit})`,
		);
	}
	if (!column) {
		style.flexDirection =
			style.flexDirection === 'row-reverse' ? 'row' : 'row-reverse';
	}
	if (column && style.alignItems) {
		style.alignItems = OPPOSITE[style.alignItems] ?? style.alignItems;
	}
	if (context.inColumn) {
		mirrorAlignSelf(style, context);
	}
	for (const [left, right] of SIDE_PAIRS) {
		swapKeys(style, left, right);
	}
	for (const key of BOX_SHORTHANDS) {
		style[key] = mirrorBoxShorthand(style[key]);
	}
	style.borderRadius = mirrorRadiusShorthand(style.borderRadius);
	if (style.textAlign) {
		style.textAlign = OPPOSITE[style.textAlign] ?? style.textAlign;
	}
	for (const key of ['objectPosition', 'backgroundPosition']) {
		if (typeof style[key] === 'string') {
			style[key] = style[key].replace(
				/\b(left|right)\b/g,
				(side) => OPPOSITE[side],
			);
		}
	}
	for (const key of Object.keys(style)) {
		if (style[key] === undefined) {
			delete style[key];
		}
	}
}

function mirrorAlignSelf(style, context) {
	if (style.alignSelf) {
		style.alignSelf = OPPOSITE[style.alignSelf] ?? style.alignSelf;
		return;
	}
	// Yoga lays out left to right, so a stretched box narrower than its column sits on the left.
	const stretched = !context.alignItems || context.alignItems === 'stretch';
	if (
		stretched &&
		(style.width !== undefined || style.maxWidth !== undefined)
	) {
		style.alignSelf = 'flex-end';
	}
}

export function isColumn(style) {
	return (style.flexDirection || '').startsWith('column');
}

function swapKeys(style, left, right) {
	const leftValue = style[left];
	style[left] = style[right];
	style[right] = leftValue;
}

function mirrorBoxShorthand(value) {
	const parts = typeof value === 'string' ? value.trim().split(/\s+/) : [];
	if (parts.length !== 4) {
		return value;
	}
	const [top, right, bottom, left] = parts;
	return [top, left, bottom, right].join(' ');
}

function mirrorRadiusShorthand(value) {
	const parts = typeof value === 'string' ? value.trim().split(/\s+/) : [];
	if (parts.length < 2 || value.includes('/')) {
		return value;
	}
	const [topLeft, topRight, bottomRight = topLeft, bottomLeft = topRight] =
		parts;
	return [topRight, topLeft, bottomLeft, bottomRight].join(' ');
}
