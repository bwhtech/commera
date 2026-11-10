// The rules of commera/localization/formatter.py; test/formatter-cases.json holds the cases both pass.
import { render_date } from './date_format.js';

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

export class Formatter {
	// The server resolves `money_formats` and `date_formats` (Formatter.as_config in Python).
	// `currency_symbols` and `money_formats` are keyed by currency code.
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
		return this.place_symbol(
			amount,
			currency,
			precision,
			this.symbol(currency),
		);
	}

	// For plain text such as a confirm dialog: a symbol drawn with HTML becomes the currency code.
	money_text(amount, currency, precision) {
		const symbol = this.symbol(currency);
		const code = currency || this.store_currency;
		const text_symbol = symbol.includes('<')
			? `${code}${NO_BREAK_SPACE}`
			: symbol;
		return this.place_symbol(amount, currency, precision, text_symbol);
	}

	// Report figures: 4.8L or 482.3K, in the language's words, with the number format's separators.
	compact_money(amount, currency) {
		const { number_format } = this.money_format(currency);
		const [sign, digits] = split_sign(this.compact(amount, number_format));
		return this.join(sign, digits, this.symbol(currency));
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

	place_symbol(amount, currency, precision, symbol) {
		const money_format = this.money_format(currency);
		const [sign, number] = split_sign(
			format_number(
				amount,
				money_format.number_format,
				precision ?? money_format.precision,
			),
		);
		return this.join(sign, number, symbol);
	}

	join(sign, digits, symbol) {
		if (this.direction === 'rtl') {
			return `${sign}${digits}${NO_BREAK_SPACE}${symbol.trim()}`;
		}
		return `${sign}${symbol}${digits}`;
	}

	symbol(currency) {
		const code = currency || this.store_currency;
		return this.currency_symbols[code] ?? `${code}${NO_BREAK_SPACE}`;
	}

	// A currency the server did not resolve takes the language's format, as Python resolves it.
	money_format(currency) {
		const resolved = this.money_formats[currency || this.store_currency];
		if (known_format(resolved?.number_format)) {
			return resolved;
		}
		const precision = NUMBER_FORMATS[this.number_format][2];
		return { number_format: this.number_format, precision };
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

// Frappe's fmt_money, precision rule included.
export function format_number(
	value,
	number_format = DEFAULT_NUMBER_FORMAT,
	requested_precision = 2,
) {
	const format_info =
		NUMBER_FORMATS[number_format] ?? NUMBER_FORMATS[DEFAULT_NUMBER_FORMAT];
	const [decimal_separator, thousands_separator] = format_info;
	const amount = Number(value) || 0;
	const precision = effective_precision(
		amount,
		requested_precision,
		format_info,
	);
	const units = round_half_even(amount, precision);
	const factor = 10 ** precision;
	const whole = String(Math.floor(Math.abs(units) / factor));
	const decimals = String(Math.abs(units) % factor).padStart(precision, '0');
	const group_size = number_format === INDIAN_NUMBER_FORMAT ? 2 : 3;
	// Like fmt_money, a format without a decimal separator drops the rounded decimals.
	const formatted =
		group_digits(whole, group_size).join(thousands_separator) +
		(precision && decimal_separator ? decimal_separator + decimals : '');
	return units < 0 && formatted !== '0' ? `-${formatted}` : formatted;
}

// fmt_money: above 2 decimals, a shorter fraction drops to its own length or the format's precision.
function effective_precision(
	amount,
	precision,
	[decimal_separator, , format_precision],
) {
	if (!decimal_separator || precision <= 2) {
		return precision;
	}
	// Python's `amount % 1` is never negative.
	const fraction = amount % 1 < 0 ? (amount % 1) + 1 : amount % 1;
	const decimals = python_decimals(
		round_half_even(fraction, precision) / 10 ** precision,
	);
	if (decimals.length < 3) {
		return format_precision;
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

// Python's round(): a tie that binary floats hold exactly goes to the even digit.
function round_half_even(amount, precision) {
	const factor = 10 ** precision;
	const absolute = Math.abs(amount);
	const scaled = absolute * factor;
	const units =
		Number.isInteger(absolute * 2 ** (precision + 1)) && scaled % 1 === 0.5
			? Math.floor(scaled) + (Math.floor(scaled) % 2)
			: Number(absolute.toFixed(precision).replace('.', ''));
	return amount < 0 ? -units : units;
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
