import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as auth from '../auth.js';
import * as orders from '../orders.js';
import { StorefrontError } from '../request.js';
import { add_fake_fetch } from './fake-fetch.js';

const items = [{ item_code: 'TEE-M', reason: 'size', comment: 'Too small' }];

const post_calls = [
	[
		'auth.send_login_code',
		() => auth.send_login_code('asha@example.com'),
		{ email: 'asha@example.com' },
	],
	[
		'auth.send_signup_code',
		() =>
			auth.send_signup_code({
				email: 'asha@example.com',
				first_name: 'Asha',
				last_name: 'Menon',
			}),
		{ email: 'asha@example.com', first_name: 'Asha', last_name: 'Menon' },
	],
	['orders.cancel_order', () => orders.cancel('SO-0001'), { name: 'SO-0001' }],
	[
		'orders.request_return',
		() => orders.request_return('SO-0001', items),
		{ name: 'SO-0001', items },
	],
	[
		'orders.send_order_link',
		() =>
			orders.send_order_link({
				order_number: 'SO-0001',
				email: 'asha@example.com',
			}),
		{ order_number: 'SO-0001', email: 'asha@example.com' },
	],
];

const get_calls = [
	[
		'orders.get_return_options',
		() => orders.get_return_options('SO-0001'),
		'name=SO-0001',
	],
	[
		'orders.get_invoice_url',
		() => orders.get_invoice_url('SO-0001'),
		'name=SO-0001',
	],
	[
		'orders.get_order_tracking',
		() => orders.get_tracking('SO-0001', 'secret'),
		'name=SO-0001&key=secret',
	],
	[
		'orders.get_order_tracking',
		() => orders.get_tracking('SO-0001'),
		'name=SO-0001',
	],
];

for (const [endpoint, call, expected_body] of post_calls) {
	test(`${endpoint} is called with POST`, async () => {
		const method = endpoint.split('.').pop();
		const calls = add_fake_fetch({ [method]: { body: { data: 'result' } } });
		assert.equal(await call(), 'result');
		assert.equal(
			calls[0].url,
			`/api/v2/method/commera.api.storefront.${endpoint}`,
		);
		assert.equal(calls[0].options.method, 'POST');
		assert.deepEqual(calls[0].body, expected_body);
	});
}

for (const [endpoint, call, expected_query] of get_calls) {
	test(`${endpoint} is called with GET ?${expected_query}`, async () => {
		const method = endpoint.split('.').pop();
		const calls = add_fake_fetch({ [method]: { body: { data: 'result' } } });
		assert.equal(await call(), 'result');
		assert.equal(
			calls[0].url,
			`/api/v2/method/commera.api.storefront.${endpoint}?${expected_query}`,
		);
		assert.equal(calls[0].options.method, 'GET');
	});
}

const profile = { email: 'asha@example.com', full_name: 'Asha Menon' };

const session_changes = [
	[
		'log_in',
		() => auth.log_in({ email: 'asha@example.com', code: '123456' }),
		{ email: 'asha@example.com', code: '123456' },
		profile,
	],
	[
		'sign_up',
		() =>
			auth.sign_up({
				email: 'asha@example.com',
				first_name: 'Asha',
				last_name: 'Menon',
				code: '123456',
			}),
		{
			email: 'asha@example.com',
			first_name: 'Asha',
			last_name: 'Menon',
			code: '123456',
		},
		profile,
	],
	['log_out', () => auth.log_out(), {}, null],
];

for (const [method, call, expected_body, result] of session_changes) {
	test(`auth.${method} returns the shopper and announces the new session`, async () => {
		const calls = add_fake_fetch({
			[method]: { body: result === null ? {} : { data: result } },
		});
		const auth_events = listen_for_auth_changes();

		assert.deepEqual(await call(), result);
		assert.equal(
			calls[0].url,
			`/api/v2/method/commera.api.storefront.auth.${method}`,
		);
		assert.deepEqual(calls[0].body, expected_body);
		assert.deepEqual(auth_events, [result]);
	});
}

test('a wrong code is a StorefrontError and changes no session', async () => {
	add_fake_fetch({
		log_in: {
			status: 417,
			body: { errors: [{ type: 'ValidationError', message: 'Invalid code' }] },
		},
	});
	const auth_events = listen_for_auth_changes();

	await assert.rejects(
		auth.log_in({ email: 'asha@example.com', code: '000000' }),
		(error) =>
			error instanceof StorefrontError &&
			error.status === 417 &&
			error.message === 'Invalid code',
	);
	assert.deepEqual(auth_events, []);
});

function listen_for_auth_changes() {
	const auth_events = [];
	const target = new EventTarget();
	target.addEventListener('commera:auth-changed', (event) =>
		auth_events.push(event.detail),
	);
	globalThis.dispatchEvent = target.dispatchEvent.bind(target);
	return auth_events;
}
