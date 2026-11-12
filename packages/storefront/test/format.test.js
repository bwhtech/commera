import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { afterEach, test } from 'node:test';
import { amount, date, money, money_text, number } from '../format.js';
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

test('money writes the riyal sign as text, labelled and left of the amount', () => {
	globalThis.commera_storefront_config = {
		number_format: '#,###.##',
		currency_symbols: { SAR: '\u20c1' },
	};
	assert.equal(
		money(1499, 'SAR'),
		'<bdi dir="ltr"><span class="currency-sign" role="img" aria-label="SAR">\u20c1</span>\u00a01,499.00</bdi>',
	);
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

test('money_text returns Unicode currency signs without HTML', () => {
	globalThis.commera_storefront_config = {
		currency_symbols: { SAR: '\u20c1', AED: '\u20c3', USD: '$' },
	};
	assert.equal(money_text(1250, 'SAR'), '\u20c1\u00a01,250.00');
	assert.equal(money_text(-1250, 'AED'), '\u20c3\u00a0-1,250.00');
	assert.equal(money_text(1250, 'USD'), '$1,250.00');
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

const amount_cases = JSON.parse(
	readFileSync(new URL('./amount-cases.json', import.meta.url)),
);

// commera/tests/test_storefront_currency.py passes the same cases with CartCurrency.amount.
test('amount prints the server digits for each number format and currency', () => {
	for (const { amount: value, expected, ...rules } of amount_cases) {
		assert.equal(amount(value, rules), expected, JSON.stringify(rules));
	}
});

test("amount without a number format takes the page's", () => {
	globalThis.commera_storefront_config = { number_format: '#,##,###.##' };
	assert.equal(amount(123456.78, { precision: 2 }), '1,23,456.78');
	globalThis.commera_storefront_config = undefined;
	assert.equal(amount(123456.78, { precision: 2 }), '123,456.78');
});

test('summer cart executes its formatter with the server config', () => {
	const template = readFileSync(
		new URL(
			'../../../commera/themes/summer_theme/pages/cart/cart.html',
			import.meta.url,
		),
		'utf8',
	);
	const method = template.match(
		/format_amount\(amount\) \{([\s\S]*?)\n\s*\}/,
	)[1];
	const source = method.replace(
		/\{\{ cart_currency.config \| tojson \}\}/g,
		'{"precision":2,"fraction_precision":2,"number_format":"#,##,###.##"}',
	);
	const format = new Function('amount', 'commera', source);
	assert.equal(format(123456.78, { format: { amount } }), '1,23,456.78');
	assert.equal(format(0, { format: { amount } }), '0.00');
});

test('all HTML money paths escape every symbol, SAR included', () => {
	const symbol = '<img src=x onerror=alert(1)> & "currency"';
	globalThis.commera_storefront_config = {
		currency_symbols: { USD: symbol, SAR: symbol },
	};
	const expected =
		'&lt;img src=x onerror=alert(1)&gt; &amp; &quot;currency&quot;';
	assert.equal(money(10, 'USD'), `${expected}10.00`);
	assert.equal(money(10, 'SAR'), `${expected}10.00`);
});
