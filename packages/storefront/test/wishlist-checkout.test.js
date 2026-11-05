import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as checkout from '../checkout.js';
import * as wishlist from '../wishlist.js';
import { add_fake_fetch } from './fake-fetch.js';

const endpoint_calls = [
	['wishlist.get_wishlist', 'GET', () => wishlist.get(), undefined],
	[
		'wishlist.add_to_wishlist',
		'POST',
		() => wishlist.add('blue-runner'),
		{ product: 'blue-runner' },
	],
	[
		'wishlist.remove_from_wishlist',
		'POST',
		() => wishlist.remove('blue-runner'),
		{ product: 'blue-runner' },
	],
	['checkout.get', 'GET', () => checkout.get(), undefined],
	['checkout.refresh', 'POST', () => checkout.refresh(), {}],
	[
		'checkout.list_pickup_locations',
		'GET',
		() => checkout.list_pickup_locations(),
		undefined,
	],
	[
		'checkout.set_addresses',
		'POST',
		() =>
			checkout.set_addresses({
				billing_address: { address_line1: '1 Main St', city: 'Pune' },
				email: 'shopper@example.com',
			}),
		{
			billing_address: { address_line1: '1 Main St', city: 'Pune' },
			email: 'shopper@example.com',
		},
	],
	[
		'checkout.set_store_pickup',
		'POST',
		() => checkout.set_store_pickup({ warehouse: 'Stores - C' }),
		{ warehouse: 'Stores - C' },
	],
	[
		'checkout.list_shipping_options',
		'GET',
		() => checkout.list_shipping_options(),
		undefined,
	],
	[
		'checkout.set_shipping_option',
		'POST',
		() => checkout.set_shipping_option('express'),
		{ option_id: 'express' },
	],
	[
		'checkout.list_payment_methods',
		'GET',
		() => checkout.list_payment_methods(),
		undefined,
	],
	[
		'checkout.start_payment',
		'POST',
		() =>
			checkout.start_payment({ payment_method: 'Stripe', expected_total: 120 }),
		{ payment_method: 'Stripe', expected_total: 120 },
	],
	[
		'checkout.complete',
		'POST',
		() => checkout.complete('PR-0001'),
		{ reference_id: 'PR-0001' },
	],
];

for (const [endpoint, http_method, call, expected_body] of endpoint_calls) {
	test(`${endpoint} is called with ${http_method}`, async () => {
		const method = endpoint.split('.').pop();
		const calls = add_fake_fetch({ [method]: { body: { data: 'result' } } });
		assert.equal(await call(), 'result');
		assert.equal(
			calls[0].url,
			`/api/v2/method/commera.api.storefront.${endpoint}`,
		);
		assert.equal(calls[0].options.method, http_method);
		assert.deepEqual(calls[0].body, expected_body);
	});
}
