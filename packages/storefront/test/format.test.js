import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { afterEach, test } from 'node:test';
import { money } from '../format.js';

const cases = JSON.parse(
	readFileSync(new URL('./fmt-money-cases.json', import.meta.url)),
);

afterEach(() => {
	globalThis.commera_storefront_config = undefined;
});

for (const [number_format, amounts] of Object.entries(cases)) {
	test(`money matches the server's fmt_money for ${number_format}`, () => {
		globalThis.commera_storefront_config = {
			number_format,
			currency_symbols: { INR: '₹' },
		};
		for (const [amount, expected] of amounts) {
			assert.equal(money(amount, 'INR'), `₹${expected}`, `amount ${amount}`);
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
