import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { beforeEach, test } from 'node:test';
import { url, localization, money } from '../index.js';

// commera/tests/test_localization_urls.py passes the same cases with the Python url().
const cases = JSON.parse(
	readFileSync(new URL('./url-cases.json', import.meta.url)),
);

function open_page(page) {
	const { language, root_prefix, prefix_codes } = cases.pages[page];
	globalThis.commera_storefront_config = {
		localization: {
			language: { code: language },
			default_language: { code: cases.languages.default },
			available_languages: cases.languages.published.map((code) => ({ code })),
			root_prefix,
			prefix_codes,
		},
	};
}

beforeEach(() => {
	globalThis.commera_storefront_config = undefined;
});

test('url matches the Python url() for each case', () => {
	for (const { page, path, expected } of cases.cases) {
		open_page(page);
		assert.equal(url(path), expected, `${page} ${JSON.stringify(path)}`);
	}
});

test('url follows the page localization set after the module loads', () => {
	assert.equal(url('/products'), '/products');
	open_page('/ar/products');
	assert.equal(url('/products'), '/ar/products');
});

test('url strips the current market prefix from a path', () => {
	globalThis.commera_storefront_config = {
		localization: {
			language: { code: 'ar' },
			default_language: { code: 'en' },
			available_languages: [{ code: 'en' }, { code: 'ar' }],
			root_prefix: '/ar-ae',
		},
	};
	assert.equal(url('/ar-ae/cart'), '/ar-ae/cart');
	assert.equal(url('/ar/cart'), '/ar-ae/cart');
	assert.equal(url('/'), '/ar-ae');
});

test('url swaps another market locale for the current one', () => {
	globalThis.commera_storefront_config = {
		localization: {
			language: { code: 'ar' },
			default_language: { code: 'en' },
			available_languages: [{ code: 'en' }, { code: 'ar' }],
			root_prefix: '/ar-ae',
			prefix_codes: ['ar', 'ar-ae', 'ar-sa', 'en', 'en-ae', 'en-sa'],
		},
	};
	assert.equal(url('/en-ae/cart'), '/ar-ae/cart');
	assert.equal(url('/ar-sa/products'), '/ar-ae/products');
});

test('localization reads the page configuration', () => {
	assert.equal(localization.language, null);
	assert.equal(localization.root_prefix, '');
	open_page('/pt-br/cart');
	assert.deepEqual(localization.language, { code: 'pt-BR' });
	assert.deepEqual(localization.default_language, { code: 'en' });
	assert.equal(localization.root_prefix, '/pt-br');
	assert.equal(localization.available_languages.length, 4);
	assert.equal(localization.market, null);
	assert.equal(localization.country, null);
});

test('money is exported at the top level', () => {
	globalThis.commera_storefront_config = {
		number_format: '#,###.##',
		store_currency: 'USD',
		currency_symbols: { USD: '$' },
		money_formats: { USD: { precision: 2, fraction_precision: 2 } },
		localization: { language: { code: 'en', direction: 'ltr' } },
	};
	assert.equal(money(1234.5), '$1,234.50');
	assert.equal(money(1234.5, 'USD'), '$1,234.50');
});
