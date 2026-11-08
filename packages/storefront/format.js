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
const PRECISION = 2;

export function money(amount, currency) {
	const { symbol, number_format } = get_currency(currency);
	return `${symbol}${format_number(amount, number_format)}`;
}

// For plain text such as a confirm dialog: a symbol drawn with HTML becomes the currency code.
export function money_text(amount, currency) {
	const { code, symbol, number_format } = get_currency(currency);
	const prefix = symbol.includes('<') ? `${code} ` : symbol;
	return `${prefix}${format_number(amount, number_format)}`;
}

function get_currency(currency) {
	const config = globalThis.commera_storefront_config ?? {};
	const code = currency || config.store_currency;
	const symbol = config.currency_symbols?.[code] ?? `${code} `;
	return { code, symbol, number_format: config.number_format };
}

function format_number(amount, number_format = '#,###.##') {
	const [decimal_separator, thousands_separator] =
		NUMBER_FORMATS[number_format] ?? NUMBER_FORMATS['#,###.##'];
	const units = round_half_even(Number(amount) || 0);
	const factor = 10 ** PRECISION;
	const whole = String(Math.floor(Math.abs(units) / factor));
	const decimals = String(Math.abs(units) % factor).padStart(PRECISION, '0');
	const group_size = number_format === '#,##,###.##' ? 2 : 3;
	const formatted =
		group_digits(whole, group_size).join(thousands_separator) +
		(decimal_separator ? decimal_separator + decimals : '');
	return units < 0 && formatted !== '0' ? `-${formatted}` : formatted;
}

function round_half_even(amount) {
	const factor = 10 ** PRECISION;
	const absolute = Math.abs(amount);
	const scaled = absolute * factor;
	const units =
		Number.isInteger(absolute * 8) && scaled % 1 === 0.5
			? Math.floor(scaled) + (Math.floor(scaled) % 2)
			: Number(absolute.toFixed(PRECISION).replace('.', ''));
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
