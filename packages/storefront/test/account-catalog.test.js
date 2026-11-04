import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as account from '../account.js';
import * as collections from '../collections.js';
import * as products from '../products.js';
import { StorefrontError } from '../request.js';
import * as shop from '../shop.js';
import { add_fake_fetch } from './fake-fetch.js';

const API_ROOT = '/api/v2/method/commera.api.storefront';
const address = { address_line1: '1 Main St', city: 'Pune', country: 'India' };

const endpoint_calls = [
	['account.get_profile', 'GET', () => account.get_profile(), '', undefined],
	[
		'account.update_profile',
		'POST',
		() => account.update_profile({ first_name: 'Asha', phone: '9800000000' }),
		'',
		{ first_name: 'Asha', phone: '9800000000' },
	],
	[
		'account.list_addresses',
		'GET',
		() => account.list_addresses(),
		'',
		undefined,
	],
	[
		'account.save_address',
		'POST',
		() => account.save_address(address),
		'',
		{ address },
	],
	[
		'account.delete_address',
		'POST',
		() => account.delete_address('ADDR-0001'),
		'',
		{ name: 'ADDR-0001' },
	],
	[
		'account.list_orders',
		'GET',
		() => account.list_orders({ page: 2, page_size: 5 }),
		'?page=2&page_size=5',
		undefined,
	],
	['account.list_orders', 'GET', () => account.list_orders(), '', undefined],
	[
		'account.get_order',
		'GET',
		() => account.get_order('SAL-ORD-0001'),
		'?name=SAL-ORD-0001',
		undefined,
	],
	[
		'account.get_order',
		'GET',
		() => account.get_order('SAL-ORD-0001', 'order-key'),
		'?name=SAL-ORD-0001&key=order-key',
		undefined,
	],
	['shop.list_countries', 'GET', () => shop.list_countries(), '', undefined],
	[
		'products.get_product',
		'GET',
		() => products.get('blue-runner'),
		'?handle=blue-runner',
		undefined,
	],
	[
		'collections.get_collections',
		'GET',
		() => collections.get_list(),
		'',
		undefined,
	],
	[
		'collections.get_collection',
		'GET',
		() => collections.get('shoes'),
		'?handle=shoes',
		undefined,
	],
];

for (const [
	endpoint,
	http_method,
	call,
	query,
	expected_body,
] of endpoint_calls) {
	test(`${endpoint}${query} is called with ${http_method}`, async () => {
		const method = endpoint.split('.').pop();
		const calls = add_fake_fetch({ [method]: { body: { data: 'result' } } });
		assert.equal(await call(), 'result');
		assert.equal(calls[0].url, `${API_ROOT}.${endpoint}${query}`);
		assert.equal(calls[0].options.method, http_method);
		assert.deepEqual(calls[0].body, expected_body);
	});
}

test('products.get_list sends list filters comma separated and on_sale as 1', async () => {
	const calls = add_fake_fetch();
	await products.get_list({
		collection: 'shoes',
		brands: ['Acme', 'Zed'],
		sizes: ['8'],
		on_sale: true,
		min_price: 0,
		sort: 'price_low',
		page: 2,
	});
	const query = new URL(calls[0].url, 'http://shop.test').searchParams;
	assert.equal(calls[0].options.method, 'GET');
	assert.deepEqual(Object.fromEntries(query), {
		collection: 'shoes',
		min_price: '0',
		sort: 'price_low',
		page: '2',
		brands: 'Acme,Zed',
		sizes: '8',
		on_sale: '1',
	});
});

test('products.get_list leaves out empty lists and a false on_sale', async () => {
	const calls = add_fake_fetch();
	await products.get_list({ query: 'runner', colors: [], on_sale: false });
	assert.equal(calls[0].url, `${API_ROOT}.products.get_products?query=runner`);
});

test('account.get_order is refused for another shopper’s order', async () => {
	add_fake_fetch({
		get_order: {
			status: 403,
			body: { errors: [{ type: 'PermissionError', message: '' }] },
		},
	});
	await assert.rejects(account.get_order('SAL-ORD-0002'), (error) => {
		assert.ok(error instanceof StorefrontError);
		assert.equal(error.status, 403);
		assert.equal(error.exc_type, 'PermissionError');
		assert.equal(error.message, 'Not permitted.');
		return true;
	});
});
