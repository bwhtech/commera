import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { afterEach, test } from 'node:test';
import { date, money, money_text, number } from '../format.js';
import { format_number } from '../formatter.js';

const cases = JSON.parse(
	readFileSync(new URL('./fmt-money-cases.json', import.meta.url)),
);

afterEach(() => {
	globalThis.commera_storefront_config = undefined;
});

for (const [number_format, amounts] of Object.entries(cases)) {
	test(`format_number matches the server's fmt_money for ${number_format}`, () => {
		for (const [amount, expected] of amounts) {
			assert.equal(
				format_number(amount, number_format, 2),
				expected,
				`amount ${amount}`,
			);
		}
	});
}

test('money keeps the SAR icon span the server renders', () => {
	const sar_symbol = '<span class="saudi-currency-symbol pe-0.5"></span>';
	globalThis.commera_storefront_config = {
		number_format: '#,###.##',
		currency_symbols: { SAR: sar_symbol },
	};
	assert.equal(money(1499, 'SAR'), `${sar_symbol}1,499.00`);
});

test('money falls back to the currency code and a no-break space', () => {
	globalThis.commera_storefront_config = {
		number_format: '#,###.##',
		currency_symbols: {},
	};
	assert.equal(money(10, 'RUB'), 'RUB 10.00');
});

test('money uses the store currency and the default format when not given', () => {
	globalThis.commera_storefront_config = {
		store_currency: 'USD',
		currency_symbols: { USD: '$' },
	};
	assert.equal(money(1234.5), '$1,234.50');
	assert.equal(money('12.3', 'USD'), '$12.30');
	assert.equal(money(null, 'USD'), '$0.00');
});

test('money_text spells out a currency whose symbol is HTML', () => {
	globalThis.commera_storefront_config = {
		currency_symbols: {
			SAR: '<span class="saudi-currency-symbol pe-0.5"></span>',
			USD: '$',
		},
	};
	assert.equal(money_text(1250, 'SAR'), 'SAR 1,250.00');
	assert.equal(money_text(1250, 'USD'), '$1,250.00');
	assert.equal(
		money(1250, 'SAR'),
		'<span class="saudi-currency-symbol pe-0.5"></span>1,250.00',
	);
});

test('money and dates read the resolved rules and the page direction', () => {
	globalThis.commera_storefront_config = {
		number_format: '#,###.##',
		currency_symbols: { INR: '₹', JPY: '¥' },
		money_formats: {
			INR: { precision: 2, fraction_precision: 2 },
			JPY: { precision: 0, fraction_precision: 2 },
		},
		date_formats: {
			parts: { medium: [{ field: 'd' }, { text: ' ' }, { field: 'MMM' }] },
			names: { MMM: ['jan', 'feb', 'mar'] },
		},
		localization: { language: { code: 'ar', direction: 'rtl' } },
	};
	assert.equal(money(1234567.5, 'INR'), '1,234,567.50\u00a0₹');
	assert.equal(money(1234.5, 'JPY'), '1,234\u00a0¥');
	assert.equal(number(1234567), '1,234,567');
	assert.equal(date('2026-03-05'), '5 mar');
});
