import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

function wishlist(call) {
	let store;
	const context = {
		document: { addEventListener: (_name, fn) => fn() },
		window: {
			addEventListener() {},
			location: { pathname: '/en-ae/account/wishlist' },
		},
		Alpine: {
			$persist: () => ({ as: () => [] }),
			store: (_name, value) => {
				store = value;
			},
		},
		fetch: call,
		with_page_localization: (url) => [
			`${url}?market=${context.window.location.pathname}`,
		],
	};
	const html = readFileSync(
		new URL(
			'../../../commera/templates/includes/wishlist-state.html',
			import.meta.url,
		),
		'utf8',
	);
	vm.runInNewContext(html.replace(/<\/?script[^>]*>/g, ''), context);
	store.items = [
		{ route: 'shoe', sale_price: 80, default_price: 100, currency: 'INR' },
	];
	store.test_window = context.window;
	return store;
}

const reply = (data) => ({ ok: true, json: async () => ({ data }) });
const product = (handle) => ({
	handle,
	price: 300,
	compare_at_price: 400,
	currency: 'AED',
	available: true,
});

test('long wishlist batches sequentially and caches adds and removals', async () => {
	let calls = 0;
	let active = 0;
	const store = wishlist(async (url) => {
		calls++;
		assert.equal(++active, 1);
		const handles = JSON.parse(
			new URL(url, 'https://shop.test').searchParams.get('handles'),
		);
		assert.ok(handles.length <= 100);
		await Promise.resolve();
		active--;
		return reply(handles.map(product));
	});
	store.items = Array.from({ length: 1000 }, (_, i) => ({
		route: `shoe-${i}`,
	}));
	await store.refresh_prices();
	assert.equal(calls, 10);
	store.remove(store.items[0]);
	await store.refresh_prices();
	assert.equal(calls, 10);
	store.items.push({ route: 'new' });
	await store.refresh_prices();
	assert.equal(calls, 11);
	assert.equal(store.display_items.at(-1).sale_price, 300);
});

for (const partial of [false, true]) {
	test(`failed batches retain items with unknown availability (partial=${partial})`, async () => {
		let calls = 0;
		const store = wishlist(async () => {
			if (!partial || ++calls > 1) throw new Error('Rate limit');
			return reply([product('shoe-0')]);
		});
		store.items = Array.from({ length: 101 }, (_, i) => ({
			route: `shoe-${i}`,
			sale_price: 80,
		}));
		await store.refresh_prices();
		assert.equal(store.items.length, 101);
		assert.equal(store.display_items.at(-1).available, undefined);
		assert.equal(store.display_items.at(-1).sale_price, null);
		assert.equal(store.prices_failed, true);
		assert.equal(store.display_items[0].sale_price, partial ? 300 : null);
	});
}

test('market changes and explicit retries refresh cached prices', async () => {
	let calls = 0;
	const store = wishlist(async () => {
		calls++;
		return reply([product('shoe')]);
	});
	await store.refresh_prices();
	assert.equal(store.items[0].sale_price, 80);
	store.test_window.location.pathname = '/ar-sa/account/wishlist';
	await store.refresh_prices();
	assert.equal(calls, 2);
	await store.refresh_prices(true);
	assert.equal(calls, 3);
});

test('removal during refresh cannot restore an entry', async () => {
	let finish;
	const store = wishlist(
		() =>
			new Promise((resolve) => {
				finish = resolve;
			}),
	);
	const refresh = store.refresh_prices();
	store.remove(store.items[0]);
	finish(reply([product('shoe')]));
	await refresh;
	assert.equal(store.display_items.length, 0);
});
