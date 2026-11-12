import { Formatter, format_number } from './formatter.js';

export { Formatter };

export function money(amount, currency) {
	return get_formatter().money(amount, currency);
}

// For plain text such as a confirm dialog: a symbol drawn with HTML becomes the currency code.
export function money_text(amount, currency) {
	return get_formatter().money_text(amount, currency);
}

// The digits of CartCurrency.amount: templates supply its config, which may be a historical
// order's currency, and print the symbol themselves.
export function amount(value, rules) {
	const number_format =
		rules.number_format ?? globalThis.commera_storefront_config?.number_format;
	return format_number(
		value,
		number_format,
		rules.precision,
		rules.fraction_precision,
	);
}

export function number(value, precision = 0) {
	return get_formatter().number(value, precision);
}

// `style` is short, medium, long or full, in the page's language.
export function date(value, style = 'medium') {
	return get_formatter().date(value, style);
}

// Read on each call: the page sets the configuration after this module loads.
function get_formatter() {
	const config = globalThis.commera_storefront_config ?? {};
	const language = config.localization?.language;
	return new Formatter({
		language: language?.code ?? config.language,
		direction: language?.direction,
		number_format: config.number_format,
		store_currency: config.store_currency,
		currency_symbols: config.currency_symbols,
		money_formats: config.money_formats,
		date_formats: config.date_formats,
	});
}
