import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import * as webmcp from '../webmcp/index.js';
import { add_fake_fetch, add_fake_window } from './fake-fetch.js';

const delivery_state = { cart: 'QUOT-1', is_store_pickup: false };
const pickup_state = { cart: 'QUOT-1', is_store_pickup: true };
const cod = { id: 'cod', title: 'Cash on delivery', is_cash_on_delivery: true };
const option_lists = {
	list_shipping_options: { body: { data: { options: [{ id: 'std' }] } } },
	list_pickup_locations: { body: { data: [{ id: 'Store - CO' }] } },
	list_payment_methods: { body: { data: [cod] } },
};
let browser;
let checkout_events;

beforeEach(() => {
	browser = add_fake_window();
	globalThis.location.pathname = '/en/cart/checkout';
	globalThis.commera_storefront_config = {
		store_currency: 'USD',
		currency_symbols: { USD: '$' },
	};
	checkout_events = [];
	const dispatch = globalThis.dispatchEvent;
	globalThis.dispatchEvent = (event) => {
		if (event.type === 'commera:checkout-updated') {
			checkout_events.push(event.detail);
		}
		return dispatch(event);
	};
});

async function call_tool(name, input) {
	const tools = new Map();
	await webmcp.register_tools({
		registerTool: async (tool) => tools.set(tool.name, tool),
	});
	return tools.get(name).execute(input);
}

test('get_checkout returns the checkout with every choice to make', async () => {
	add_fake_fetch({ get: { body: { data: delivery_state } }, ...option_lists });
	const { structuredContent } = await call_tool('get_checkout', {});
	assert.deepEqual(structuredContent, {
		checkout: delivery_state,
		shipping_options: [{ id: 'std' }],
		shipping_options_reason: null,
		pickup_locations: [{ id: 'Store - CO' }],
		payment_methods: [cod],
	});
});

test('get_checkout skips shipping options for store pickup', async () => {
	const calls = add_fake_fetch({
		get: { body: { data: pickup_state } },
		...option_lists,
	});
	const { structuredContent } = await call_tool('get_checkout', {});
	assert.equal(structuredContent.shipping_options_reason, 'store_pickup');
	assert.ok(!calls.some((call) => call.method === 'list_shipping_options'));
});

test('update_checkout bills the shipping address and tells the page', async () => {
	const address = {
		first_name: 'Asha',
		address_line1: '1 Main St',
		city: 'Pune',
		pincode: '411001',
		country: 'India',
	};
	const calls = add_fake_fetch({
		set_addresses: { body: { data: delivery_state } },
		set_shipping_option: {
			body: { data: { ...delivery_state, shipping_option: 'std' } },
		},
		...option_lists,
	});
	const result = await call_tool('update_checkout', {
		email: 'asha@example.com',
		shipping_address: address,
		shipping_option: 'std',
	});
	assert.deepEqual(calls[0].body, {
		billing_address: address,
		email: 'asha@example.com',
	});
	assert.deepEqual(calls[1].body, { option_id: 'std' });
	assert.equal(result.structuredContent.checkout.shipping_option, 'std');
	assert.deepEqual(checkout_events, [
		delivery_state,
		{ ...delivery_state, shipping_option: 'std' },
	]);
});

test('update_checkout sends a separate billing address as billing', async () => {
	const calls = add_fake_fetch({
		set_addresses: { body: { data: delivery_state } },
		...option_lists,
	});
	await call_tool('update_checkout', {
		shipping_address: 'ADDR-SHIP',
		billing_address: 'ADDR-BILL',
	});
	assert.deepEqual(calls[0].body, {
		billing_address: 'ADDR-BILL',
		shipping_address: 'ADDR-SHIP',
	});
});

test('update_checkout picks a store for pickup', async () => {
	const calls = add_fake_fetch({
		set_store_pickup: { body: { data: pickup_state } },
		...option_lists,
	});
	await call_tool('update_checkout', { pickup_location: 'Store - CO' });
	assert.deepEqual(calls[0].body, { warehouse: 'Store - CO' });
});

for (const [input, message] of [
	[
		{ pickup_location: 'Store - CO', shipping_address: 'ADDR-SHIP' },
		'Send an address or a pickup location, not both.',
	],
	[
		{ email: 'asha@example.com' },
		'Send a billing address or email together with a shipping address.',
	],
	[{}, 'Send a shipping address, a pickup location or a shipping option.'],
]) {
	test(`update_checkout refuses ${JSON.stringify(input)}`, async () => {
		const calls = add_fake_fetch();
		const result = await call_tool('update_checkout', input);
		assert.deepEqual(result.content[0].text, message);
		assert.equal(calls.length, 0);
	});
}

const reviewed_state = {
	cart: 'QUOT-1',
	version: 'v1',
	currency: 'USD',
	items: [{ item_code: 'PADS-L', title: 'Brake Pads', qty: 2 }],
	email: 'asha@example.com',
	is_store_pickup: false,
	shipping_address: {
		address_line1: '1 MG Road',
		city: 'Pune',
		country: 'India',
	},
	summary: { total: 1300, cash_on_delivery: { total: 1250 } },
};
const placing_order = {
	...option_lists,
	get: { body: { data: reviewed_state } },
};

test('complete_checkout shows the buyer the order the store holds', async () => {
	const questions = [];
	globalThis.confirm = (question) => questions.push(question) && false;
	const calls = add_fake_fetch(placing_order);
	const result = await call_tool('complete_checkout', {
		payment_method: 'cod',
	});
	assert.equal(
		questions[0],
		[
			'Place this order?',
			'',
			'2 × Brake Pads',
			'',
			'Deliver to: 1 MG Road, Pune, India',
			'Email: asha@example.com',
			'Payment: Cash on delivery',
			'Total: $1,250.00',
		].join('\n'),
	);
	assert.equal(result.content[0].text, 'The buyer did not confirm the order.');
	assert.ok(!calls.some((call) => call.method === 'start_payment'));
});

test('complete_checkout pays the reviewed total and checkout version', async () => {
	globalThis.confirm = () => true;
	const calls = add_fake_fetch({
		...placing_order,
		start_payment: {
			body: { data: { redirect_url: '/pay/QUOT-1', reference_id: 'QUOT-1' } },
		},
	});
	await call_tool('complete_checkout', { payment_method: 'cod' });
	assert.deepEqual(calls.at(-1).body, {
		payment_method: 'cod',
		expected_total: 1250,
		expected_version: 'v1',
	});
	assert.deepEqual(browser.assigned, ['/pay/QUOT-1']);
});

test('complete_checkout needs a checkout and a known payment method', async () => {
	globalThis.confirm = () => assert.fail('asked the buyer');
	add_fake_fetch({ ...placing_order, get: { body: { data: null } } });
	let result = await call_tool('complete_checkout', { payment_method: 'cod' });
	assert.equal(
		result.content[0].text,
		'Save the delivery details with update_checkout first.',
	);

	add_fake_fetch(placing_order);
	result = await call_tool('complete_checkout', { payment_method: 'crypto' });
	assert.equal(
		result.content[0].text,
		'The store has no payment method crypto.',
	);
});

test('update_checkout shows a saved address even when the shipping option fails', async () => {
	add_fake_fetch({
		set_addresses: { body: { data: delivery_state } },
		set_shipping_option: {
			status: 417,
			body: { errors: [{ message: 'That option does not ship there.' }] },
		},
	});
	const result = await call_tool('update_checkout', {
		shipping_address: 'ADDR-SHIP',
		shipping_option: 'express',
	});
	assert.equal(
		result.content[0].text,
		'Saved the delivery details, but not the shipping option: That option does not ship there.',
	);
	assert.deepEqual(checkout_events, [delivery_state]);
});

test('update_checkout marks its result untrusted', async () => {
	const tools = new Map();
	await webmcp.register_tools({
		registerTool: async (tool) => tools.set(tool.name, tool),
	});
	assert.deepEqual(tools.get('update_checkout').annotations, {
		untrustedContentHint: true,
	});
	assert.deepEqual(tools.get('complete_checkout').annotations, {
		consequentialHint: true,
	});
});
