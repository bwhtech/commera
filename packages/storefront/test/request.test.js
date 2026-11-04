import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { StorefrontError, get, post } from '../request.js';
import { add_fake_fetch } from './fake-fetch.js';

beforeEach(() => {
	globalThis.commera_storefront_config = { csrf_token: 'csrf-123' };
	globalThis.frappe = undefined;
});

test('get sends arguments in the query string and unwraps data', async () => {
	const calls = add_fake_fetch({
		get_products: { body: { data: { products: [] } } },
	});
	const result = await get('products.get_products', {
		collection: 'shoes',
		brands: ['Nike', 'Puma'],
		query: null,
	});
	assert.deepEqual(result, { products: [] });
	assert.equal(
		calls[0].url,
		'/api/v2/method/commera.api.storefront.products.get_products?collection=shoes&brands=%5B%22Nike%22%2C%22Puma%22%5D',
	);
	assert.equal(calls[0].options.method, 'GET');
	assert.equal(calls[0].options.credentials, 'same-origin');
});

test('get without arguments has no query string', async () => {
	const calls = add_fake_fetch();
	await get('cart.get_cart');
	assert.equal(
		calls[0].url,
		'/api/v2/method/commera.api.storefront.cart.get_cart',
	);
});

test('post sends a JSON body with the CSRF token', async () => {
	const calls = add_fake_fetch();
	await post('cart.add_lines', { lines: [{ item_code: 'SHOE-42', qty: 1 }] });
	assert.equal(calls[0].options.method, 'POST');
	assert.equal(calls[0].options.headers['X-Frappe-CSRF-Token'], 'csrf-123');
	assert.equal(calls[0].options.headers['Content-Type'], 'application/json');
	assert.deepEqual(calls[0].body, {
		lines: [{ item_code: 'SHOE-42', qty: 1 }],
	});
});

test('post falls back to frappe.csrf_token on a page without the config', async () => {
	globalThis.commera_storefront_config = undefined;
	globalThis.frappe = { csrf_token: 'desk-csrf' };
	const calls = add_fake_fetch();
	await post('cart.get_checkout_url');
	assert.equal(calls[0].options.headers['X-Frappe-CSRF-Token'], 'desk-csrf');
});

test('a failed call throws the error message without HTML', async () => {
	add_fake_fetch({
		add_discount_code: {
			status: 417,
			body: {
				errors: [
					{
						type: 'ValidationError',
						message: 'Code <b>SAVE10</b> has expired',
						exception:
							'frappe.exceptions.ValidationError: Code SAVE10 has expired',
					},
				],
			},
		},
	});
	await assert.rejects(post('cart.add_discount_code', { code: 'SAVE10' }), {
		name: 'StorefrontError',
		message: 'Code SAVE10 has expired',
		status: 417,
		exc_type: 'ValidationError',
	});
});

test('a failed call without an error message throws the first message', async () => {
	add_fake_fetch({
		set_addresses: {
			status: 417,
			body: {
				errors: [{ type: 'ValidationError' }],
				messages: [{ message: 'Please enter a <i>city</i>' }],
			},
		},
	});
	await assert.rejects(post('checkout.set_addresses', {}), {
		message: 'Please enter a city',
		exc_type: 'ValidationError',
	});
});

test('a failed call without messages throws the last line of the traceback', async () => {
	add_fake_fetch({
		get_wishlist: {
			status: 403,
			body: {
				errors: [
					{
						type: 'PermissionError',
						exception:
							'Traceback (most recent call last):\n  File "app.py"\nfrappe.exceptions.PermissionError\n',
					},
				],
			},
		},
	});
	const error = await get('wishlist.get_wishlist').catch((error) => error);
	assert.ok(error instanceof StorefrontError);
	assert.equal(error.message, 'frappe.exceptions.PermissionError');
	assert.equal(error.exc_type, 'PermissionError');
});

test('a failed call with only the error type throws the status text', async () => {
	add_fake_fetch({
		get_product: {
			status: 417,
			body: { errors: [{ type: 'ValidationError' }] },
		},
	});
	await assert.rejects(get('products.get_product', { handle: 'gone' }), {
		message: 'Error',
		status: 417,
		exc_type: 'ValidationError',
	});
});

test('a failed call with no JSON body throws the status text', async () => {
	globalThis.fetch = async () => ({
		ok: false,
		status: 502,
		statusText: 'Bad Gateway',
		json: async () => {
			throw new SyntaxError('Unexpected token <');
		},
	});
	await assert.rejects(get('cart.get_cart'), {
		message: 'Bad Gateway',
		status: 502,
	});
});

test('a call that never reaches the store throws a StorefrontError with status 0', async () => {
	const network_error = new TypeError('Load failed');
	globalThis.fetch = async () => {
		throw network_error;
	};
	const error = await get('cart.get_cart').catch((error) => error);
	assert.ok(error instanceof StorefrontError);
	assert.equal(error.message, 'Could not reach the store.');
	assert.equal(error.status, 0);
	assert.equal(error.cause, network_error);
});

test('a successful call that is not JSON throws instead of returning undefined', async () => {
	globalThis.fetch = async () => ({
		ok: true,
		status: 200,
		statusText: 'OK',
		json: async () => {
			throw new SyntaxError('Unexpected token <');
		},
	});
	await assert.rejects(get('search.get_typeahead', { query: 'shirt' }), {
		name: 'StorefrontError',
		message: 'The store sent an unexpected response.',
		status: 200,
	});
});

test('a call whose answer is None returns null', async () => {
	add_fake_fetch({ get_cart: { body: {} } });
	assert.equal(await get('cart.get_cart'), null);
});

for (const [status, exc_type, message] of [
	[404, 'DoesNotExistError', 'Not found.'],
	[403, 'PermissionError', 'Not permitted.'],
]) {
	test(`a ${status} with no message behind a proxy reads "${message}"`, async () => {
		globalThis.fetch = async () => ({
			ok: false,
			status,
			statusText: '',
			json: async () => ({ errors: [{ type: exc_type }] }),
		});
		await assert.rejects(get('products.get_product', { handle: 'gone' }), {
			name: 'StorefrontError',
			message,
			status,
			exc_type,
		});
	});
}

test('a server message still wins over the fallback', async () => {
	add_fake_fetch({
		get_product: {
			status: 404,
			body: {
				errors: [
					{ type: 'DoesNotExistError', message: 'Product gone not found' },
				],
			},
		},
	});
	await assert.rejects(get('products.get_product', { handle: 'gone' }), {
		message: 'Product gone not found',
	});
});
