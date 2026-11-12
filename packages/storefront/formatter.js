// The rules of commera/localization/formatter.py; test/formatter-cases.json holds the cases both pass.
import { render_date } from './date_format.js';
import { python_fixed, python_round } from './decimal.js';

const NUMBER_FORMATS = {
	'#,###.##': ['.', ',', 2],
	'#.###,##': [',', '.', 2],
	'# ###.##': ['.', ' ', 2],
	'# ###,##': [',', ' ', 2],
	"#'###.##": ['.', "'", 2],
	'#, ###.##': ['.', ', ', 2],
	'#,##,###.##': ['.', ',', 2],
	'#,###.###': ['.', ',', 3],
	'#.###': ['', '.', 0],
	'#,###': ['', ',', 0],
	'#.########': ['.', '', 8],
};
const DEFAULT_NUMBER_FORMAT = '#,###.##';
const INDIAN_NUMBER_FORMAT = '#,##,###.##';
const DATE_STYLES = ['short', 'medium', 'long', 'full'];
const NO_BREAK_SPACE = '\u00a0';
// Intl wraps a right-to-left sign in these; the symbol placement already orders the parts.
const BIDI_MARKS = /[\u061c\u200e\u200f]/g;
// The Saudi riyal and UAE dirham signs, newer (Unicode 17, 18) than most fonts and screen readers.
const CURRENCY_SIGNS = ['\u20c1', '\u20c3'];

export class Formatter {
	// The server resolves `money_formats` and `date_formats` (Formatter.as_config in Python).
	// `money_formats` holds each currency's precision and fraction_precision, by currency code.
	constructor({
		language = 'en',
		direction = 'ltr',
		number_format,
		store_currency,
		currency_symbols = {},
		money_formats = {},
		date_formats,
	} = {}) {
		this.language = language;
		this.direction = direction;
		this.number_format = known_format(number_format) ?? DEFAULT_NUMBER_FORMAT;
		this.store_currency = store_currency;
		this.currency_symbols = currency_symbols;
		this.money_formats = money_formats;
		this.date_formats = date_formats;
	}

	money(amount, currency, precision) {
		return this.join_html(this.digits(amount, currency, precision), currency);
	}

	money_text(amount, currency, precision) {
		const formatted = this.digits(amount, currency, precision);
		const symbol = this.symbol(currency);
		if (this.is_sign(currency)) {
			return `${symbol}${NO_BREAK_SPACE}${formatted.replace(/^-/, '−')}`;
		}
		const [sign, digits] = split_sign(formatted);
		return this.join(sign, digits, symbol);
	}

	signed_money(amount, currency, minus = '−') {
		if (this.is_sign(currency)) {
			return this.money(amount, currency);
		}
		return (amount < 0 ? minus : '') + this.money(Math.abs(amount), currency);
	}

	// Report figures: 4.8L or 482.3K, in the language's words, with the number format's separators.
	compact_money(amount, currency) {
		return this.join_html(this.compact(amount, this.number_format), currency);
	}

	number(value, precision = 0) {
		return format_number(value, this.number_format, precision);
	}

	date(value, style = 'medium') {
		const date = to_utc_date(value);
		if (!date) {
			return '';
		}
		if (!DATE_STYLES.includes(style)) {
			throw new RangeError(
				`Date style must be one of ${DATE_STYLES.join(', ')}.`,
			);
		}
		if (this.date_formats?.parts) {
			return render_date(date, this.date_formats, style);
		}
		// Without the server's patterns: Gregorian and Latin digits, close to Babel.
		return new Intl.DateTimeFormat([this.language, 'en'], {
			dateStyle: style,
			timeZone: 'UTC',
			calendar: 'gregory',
			numberingSystem: 'latn',
		}).format(date);
	}

	digits(amount, currency, precision) {
		const { precision: money_precision, fraction_precision } =
			this.money_format(currency);
		return format_number(
			amount,
			this.number_format,
			precision ?? money_precision,
			fraction_precision,
		);
	}

	join(sign, digits, symbol) {
		if (this.direction === 'rtl') {
			return `${sign}${digits}${NO_BREAK_SPACE}${symbol.trim()}`;
		}
		return `${sign}${symbol}${digits}`;
	}

	// SAMA and the CBUAE put a sign left of the amount, and of a minus sign, on any page.
	join_html(formatted, currency) {
		const symbol = this.html_symbol(currency);
		if (this.is_sign(currency)) {
			return `<bdi dir="ltr">${symbol}${formatted.replace(/^-/, '−')}</bdi>`;
		}
		const [sign, digits] = split_sign(formatted);
		return this.join(sign, digits, symbol);
	}

	// Screen readers may not know the new signs yet, so a sign reads as its currency code.
	html_symbol(currency) {
		const symbol = escape_html(this.symbol(currency));
		if (!this.is_sign(currency)) {
			return symbol;
		}
		const label = escape_html(this.code(currency));
		return `<span class="currency-sign" role="img" aria-label="${label}">${symbol}</span>${NO_BREAK_SPACE}`;
	}

	is_sign(currency) {
		return CURRENCY_SIGNS.includes(this.symbol(currency));
	}

	symbol(currency) {
		const code = this.code(currency);
		return this.currency_symbols[code] ?? `${code}${NO_BREAK_SPACE}`;
	}

	code(currency) {
		return currency || this.store_currency;
	}

	// A currency the server did not resolve takes the format's precision and fmt_money's 100 units.
	money_format(currency) {
		const resolved = this.money_formats[currency || this.store_currency];
		if (Number.isInteger(resolved?.precision)) {
			return resolved;
		}
		const precision = NUMBER_FORMATS[this.number_format][2];
		return { precision, fraction_precision: 2 };
	}

	compact(amount, number_format) {
		const [decimal_separator, thousands_separator] =
			NUMBER_FORMATS[number_format];
		const base_language = this.language.split('-')[0];
		// Only an Indian region prints lakh and crore, so the Indian number format asks for one.
		const locale =
			number_format === INDIAN_NUMBER_FORMAT
				? `${base_language}-IN`
				: this.language;
		const decimal =
			decimal_separator || (thousands_separator === '.' ? ',' : '.');
		const separators = { decimal, group: thousands_separator };
		return new Intl.NumberFormat([locale, 'en'], {
			notation: 'compact',
			maximumFractionDigits: 1,
			numberingSystem: 'latn',
		})
			.formatToParts(Number(amount) || 0)
			.map((part) =>
				part.type === 'minusSign' ? '-' : separators[part.type] ?? part.value,
			)
			.join('')
			.replace(BIDI_MARKS, '');
	}
}

// Frappe's fmt_money, precision rules included.
export function format_number(
	value,
	number_format = DEFAULT_NUMBER_FORMAT,
	requested_precision = 2,
	fraction_precision = undefined,
) {
	const format_info =
		NUMBER_FORMATS[number_format] ?? NUMBER_FORMATS[DEFAULT_NUMBER_FORMAT];
	const [decimal_separator, thousands_separator] = format_info;
	const amount = Number.isFinite(Number(value)) ? Number(value) : 0;
	const precision = effective_precision(
		amount,
		requested_precision,
		format_info,
		fraction_precision,
	);
	const [whole, decimals = ''] = python_fixed(amount, precision).split('.');
	const group_size = number_format === INDIAN_NUMBER_FORMAT ? 2 : 3;
	// Like fmt_money, a format without a decimal separator drops the rounded decimals.
	const formatted =
		group_digits(whole, group_size).join(thousands_separator) +
		(precision && decimal_separator ? decimal_separator + decimals : '');
	const negative = amount < 0 && /[1-9]/.test(whole + decimals);
	return negative && formatted !== '0' ? `-${formatted}` : formatted;
}

// fmt_money: above 2 decimals, a shorter fraction drops to its own length, or to the currency's
// fraction units (the format's precision when there is no currency).
function effective_precision(
	amount,
	precision,
	[decimal_separator, , format_precision],
	fraction_precision,
) {
	if (!decimal_separator || precision <= 2) {
		return precision;
	}
	// Python's `amount % 1` is never negative.
	const fraction = amount % 1 < 0 ? (amount % 1) + 1 : amount % 1;
	const decimals = python_decimals(python_round(fraction, precision));
	if (decimals.length < 3) {
		return fraction_precision ?? format_precision;
	}
	return Math.min(decimals.length, precision);
}

// What fmt_money reads after the point of str(x) for 0 <= x <= 1; Python writes 1.2e-05 below 1e-4.
function python_decimals(x) {
	const text =
		x > 0 && x < 1e-4
			? x.toExponential().replace(/e-(\d)$/, 'e-0$1')
			: String(x);
	const parts = text.split('.');
	return parts.length > 1 ? parts[1] : parts[0];
}

function known_format(number_format) {
	return number_format in NUMBER_FORMATS ? number_format : undefined;
}

function split_sign(formatted) {
	return formatted.startsWith('-')
		? ['-', formatted.slice(1)]
		: ['', formatted];
}

// A date-only string or a datetime string keeps its calendar day; a Date keeps its local day.
function to_utc_date(value) {
	if (!value) {
		return null;
	}
	if (value instanceof Date) {
		return new Date(
			Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()),
		);
	}
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
	return match ? new Date(Date.UTC(match[1], match[2] - 1, match[3])) : null;
}

function group_digits(whole, group_size) {
	if (whole.length <= 3) {
		return [whole];
	}
	const groups = [whole.slice(-3)];
	let rest = whole.slice(0, -3);
	while (rest.length > group_size) {
		groups.unshift(rest.slice(-group_size));
		rest = rest.slice(0, -group_size);
	}
	groups.unshift(rest);
	return groups;
}

const HTML_ENTITIES = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#x27;',
};

function escape_html(text) {
	return String(text).replace(
		/[&<>"']/g,
		(character) => HTML_ENTITIES[character],
	);
}
