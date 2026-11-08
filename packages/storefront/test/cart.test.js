import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import * as cart from '../cart.js';
import { add_fake_fetch, add_fake_window } from './fake-fetch.js';

const priced_cart = { name: 'CART-0001', total_quantity: 1, lines: [] };
let browser;

beforeEach(() => {
	browser = add_fake_window();
});

const cart_writes = [
	[
		'add_lines',
		() => cart.add_lines([{ item_code: 'SHOE-42', qty: 2 }]),
		{ lines: [{ item_code: 'SHOE-42', qty: 2 }] },
	],
	[
		'update_lines',
		() => cart.update_lines([{ line_id: 'line-1', qty: 0 }]),
		{ lines: [{ line_id: 'line-1', qty: 0 }] },
	],
	[
		'set_lines',
		() => cart.set_lines([{ line_id: 'line-1', qty: 2 }], 4),
		{ lines: [{ line_id: 'line-1', qty: 2 }], revision: 4 },
	],
	[
		'remove_lines',
		() => cart.remove_lines(['line-1']),
		{ line_ids: ['line-1'] },
	],
	[
		'add_discount_code',
		() => cart.apply_discount('SAVE10'),
		{ code: 'SAVE10' },
	],
	[
		'remove_discount_code',
		() => cart.remove_discount('SAVE10'),
		{ code: 'SAVE10' },
	],
];

for (const [method, call, expected_body] of cart_writes) {
	test(`${method} posts its arguments and announces the new cart`, async () => {
		const calls = add_fake_fetch({
			[method]: { body: { data: priced_cart } },
		});
		const result = await call();
		assert.equal(
			calls[0].url,
			`/api/v2/method/commera.api.storefront.cart.${method}`,
		);
		assert.equal(calls[0].options.method, 'POST');
		assert.deepEqual(calls[0].body, expected_body);
		assert.deepEqual(result, priced_cart);
		assert.deepEqual(browser.events, [priced_cart]);
	});
}

test('get reads the cart without announcing it', async () => {
	const calls = add_fake_fetch({
		get_cart: { body: { data: priced_cart } },
	});
	assert.deepEqual(await cart.get(), priced_cart);
	assert.equal(calls[0].options.method, 'GET');
	assert.deepEqual(browser.events, []);
});

test('a failed write throws and announces nothing', async () => {
	add_fake_fetch({
		add_lines: {
			status: 417,
			body: { errors: [{ type: 'ValidationError', message: 'Out of stock' }] },
		},
	});
	await assert.rejects(cart.add_lines([{ item_code: 'SHOE-42' }]), {
		message: 'Out of stock',
	});
	assert.deepEqual(browser.events, []);
});

test('go_to_checkout opens the single-use checkout path', async () => {
	const path =
		'/api/v2/method/commera.api.storefront.cart.open_checkout?code=abc';
	const calls = add_fake_fetch({
		get_checkout_url: { body: { data: { path } } },
	});
	await cart.go_to_checkout();
	assert.equal(calls[0].options.method, 'POST');
	assert.deepEqual(browser.assigned, [path]);
});

test('a later write waits for the earlier one, so the newest cart is announced last', async () => {
	const replies = [];
	globalThis.fetch = (url) =>
		new Promise((resolve) => {
			const method = url.split('.').pop();
			replies.push(() =>
				resolve({
					ok: true,
					status: 200,
					json: async () => ({ data: { name: method } }),
				}),
			);
		});
	const first = cart.add_lines([{ item_code: 'SHOE-42', qty: 1 }]);
	const second = cart.remove_lines(['line-1']);
	await new Promise((resolve) => setTimeout(resolve));
	assert.equal(replies.length, 1, 'the second write was sent before the first answered');
	replies[0]();
	await first;
	await new Promise((resolve) => setTimeout(resolve));
	replies[1]();
	await second;
	assert.deepEqual(
		browser.events.map((event) => event.name),
		['add_lines', 'remove_lines'],
	);
});

test('a failed write does not hold up the next one', async () => {
	add_fake_fetch({
		add_lines: { status: 417, body: { errors: [{ message: 'Out of stock' }] } },
		remove_lines: { body: { data: priced_cart } },
	});
	await assert.rejects(cart.add_lines([{ item_code: 'SHOE-42', qty: 9 }]));
	assert.deepEqual(await cart.remove_lines(['line-1']), priced_cart);
});
