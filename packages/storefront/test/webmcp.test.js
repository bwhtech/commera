import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { StorefrontError } from '../request.js';
import * as webmcp from '../webmcp.js';
import { add_fake_fetch, add_fake_window } from './fake-fetch.js';

const two_line_cart = {
	version: '2026-11-08 10:00:00',
	lines: [
		{ line_id: 'line-1', item_code: 'SHOE-42', qty: 1 },
		{ line_id: 'line-2', item_code: 'SOCK-M', qty: 2 },
	],
};
let browser;

beforeEach(() => {
	browser = add_fake_window();
	globalThis.location.pathname = '/ar/products';
	globalThis.commera_storefront_config = { language: 'ar' };
});

function add_fake_model_context() {
	const tools = new Map();
	return {
		tools,
		registerTool: async (tool) => tools.set(tool.name, tool),
	};
}

async function call_tool(name, input) {
	const model_context = add_fake_model_context();
	await webmcp.register_tools(model_context);
	return model_context.tools.get(name).execute(input);
}

test('register_tools does nothing without WebMCP', async () => {
	assert.deepEqual(await webmcp.register_tools(undefined), []);
});

test('storefront pages get catalog and cart tools, checkout gets its own', async () => {
	const storefront = add_fake_model_context();
	await webmcp.register_tools(storefront);
	assert.deepEqual(
		[...storefront.tools.keys()],
		[
			'search_catalog',
			'browse_store',
			'get_product',
			'show_product',
			'get_cart',
			'update_cart',
			'clear_cart',
			'proceed_to_checkout',
		],
	);
	assert.equal(storefront.tools.get('get_cart').annotations.readOnlyHint, true);
	for (const name of ['update_cart', 'clear_cart']) {
		assert.deepEqual(storefront.tools.get(name).annotations, {
			untrustedContentHint: true,
		});
	}

	globalThis.location.pathname = '/en/cart/checkout';
	const checkout = add_fake_model_context();
	await webmcp.register_tools(checkout);
	assert.deepEqual(
		[...checkout.tools.keys()],
		['get_checkout', 'navigate_to_storefront'],
	);
});

test('search_catalog gives each product a page URL in the shop language', async () => {
	const calls = add_fake_fetch({
		get_typeahead: {
			body: {
				data: { query: 'red shoe', products: [{ handle: 'red shoe' }] },
			},
		},
	});
	const result = await call_tool('search_catalog', { query: 'red shoe' });
	assert.match(
		calls[0].url,
		/search\.get_typeahead\?query=red\+shoe&_lang=ar$/,
	);
	assert.deepEqual(result.structuredContent.products, [
		{ handle: 'red shoe', url: '/ar/products/red%20shoe' },
	]);
	assert.equal(
		result.structuredContent.search_url,
		'/ar/products?search=red+shoe',
	);
	assert.deepEqual(
		JSON.parse(result.content[0].text),
		result.structuredContent,
	);
});

test('browse_store lists collections without a collection handle', async () => {
	add_fake_fetch({
		get_collections: { body: { data: [{ handle: 'shoes' }] } },
	});
	const result = await call_tool('browse_store', {});
	assert.deepEqual(result.structuredContent.collections, [
		{ handle: 'shoes', url: '/ar/products?category=shoes' },
	]);
});

test('update_cart changes, removes and adds lines to match the request', async () => {
	const calls = add_fake_fetch({
		get_cart: { body: { data: two_line_cart } },
		update_lines: { body: { data: { version: 'b' } } },
		add_lines: { body: { data: { version: 'c' } } },
	});
	const result = await call_tool('update_cart', {
		version: two_line_cart.version,
		lines: [
			{ line_id: 'line-1', qty: 3 },
			{ item_code: 'HAT-1', qty: 1 },
		],
	});
	assert.deepEqual(calls[1].body, {
		lines: [
			{ line_id: 'line-1', qty: 3 },
			{ line_id: 'line-2', qty: 0 },
		],
		_lang: 'ar',
	});
	assert.deepEqual(calls[2].body, {
		lines: [{ item_code: 'HAT-1', qty: 1 }],
		_lang: 'ar',
	});
	assert.deepEqual(result.structuredContent, {
		cart: { version: 'c' },
		changed: true,
	});
});

test('update_cart leaves a cart alone when it changed since the agent read it', async () => {
	const calls = add_fake_fetch({ get_cart: { body: { data: two_line_cart } } });
	const result = await call_tool('update_cart', {
		version: 'an older version',
		lines: [],
	});
	assert.equal(calls.length, 1);
	assert.equal(result.structuredContent.changed, false);
	assert.deepEqual(result.structuredContent.cart, two_line_cart);
});

test('update_cart adds the first lines to an empty cart', async () => {
	const calls = add_fake_fetch({
		get_cart: { body: { data: null } },
		add_lines: { body: { data: { version: 'a' } } },
	});
	await call_tool('update_cart', {
		version: null,
		lines: [{ item_code: 'SHOE-42', qty: 1 }],
	});
	assert.deepEqual(
		calls.map((call) => call.method),
		['get_cart', 'add_lines'],
	);
});

test('update_cart reports a line the cart does not have', async () => {
	add_fake_fetch({ get_cart: { body: { data: two_line_cart } } });
	const result = await call_tool('update_cart', {
		version: two_line_cart.version,
		lines: [{ line_id: 'line-9', qty: 1 }],
	});
	assert.equal(result.isError, true);
	assert.equal(result.content[0].text, 'The cart has no line line-9.');
});

test('clear_cart removes every line', async () => {
	const calls = add_fake_fetch({
		get_cart: { body: { data: two_line_cart } },
		remove_lines: { body: { data: null } },
	});
	await call_tool('clear_cart', {});
	assert.deepEqual(calls[1].body, {
		line_ids: ['line-1', 'line-2'],
		_lang: 'ar',
	});
});

test('proceed_to_checkout refuses an empty cart', async () => {
	add_fake_fetch({ get_cart: { body: { data: null } } });
	const result = await call_tool('proceed_to_checkout', {});
	assert.equal(result.isError, true);
	assert.deepEqual(browser.assigned, []);
});

test('proceed_to_checkout opens checkout for a cart with lines', async () => {
	add_fake_fetch({
		get_cart: { body: { data: two_line_cart } },
		get_checkout_url: { body: { data: { path: '/en/cart/checkout' } } },
	});
	await call_tool('proceed_to_checkout', {});
	assert.deepEqual(browser.assigned, ['/en/cart/checkout']);
});

test('a store error becomes a tool error and a bug still throws', async () => {
	add_fake_fetch({
		get_product: {
			status: 404,
			body: { errors: [{ message: 'Product gone not found' }] },
		},
	});
	const result = await call_tool('get_product', { handle: 'gone' });
	assert.deepEqual(result, {
		isError: true,
		content: [{ type: 'text', text: 'Product gone not found' }],
	});

	globalThis.fetch = async () => ({
		ok: true,
		status: 200,
		json: async () => ({ data: { products: null } }),
	});
	await assert.rejects(
		call_tool('search_catalog', { query: 'shoe' }),
		(error) => !(error instanceof StorefrontError),
	);
});
