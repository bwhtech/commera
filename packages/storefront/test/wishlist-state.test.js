import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

function wishlist(call) {
	let store;
	const context = {
		document: { addEventListener: (_name, fn) => fn() },
		window: { addEventListener() {} },
		Alpine: {
			$persist: () => ({ as: () => [] }),
			store: (_name, value) => {
				store = value;
			},
		},
		frappe_call: call,
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
	return store;
}

test('persisted wishlist hides old amounts until market product prices arrive', async () => {
	let finish;
	const store = wishlist((url, args, method) => {
		assert.match(url, /get_product\?handle=shoe$/);
		assert.equal(method, 'GET');
		return new Promise((resolve) => {
			finish = resolve;
		});
	});
	const refresh = store.refresh_prices();
	assert.equal(store.prices_ready, false);
	assert.equal(store.display_items[0].sale_price, null);
	finish({
		data: {
			price: 300,
			currency: 'AED',
			available: true,
			variants: [{ price: 300, compare_at_price: 400 }],
		},
	});
	await refresh;
	assert.equal(store.prices_ready, true);
	assert.equal(store.display_items[0].sale_price, 300);
	assert.equal(store.display_items[0].default_price, 400);
	assert.equal(store.display_items[0].currency, 'AED');
	assert.equal(store.display_items[0].available, true);
});

for (const missing of [false, true]) {
	test(`wishlist retains unavailable product without stale amounts (missing=${missing})`, async () => {
		const store = wishlist(async () => {
			if (missing) throw new Error('Removed');
			return {
				data: { price: null, currency: 'AED', available: false, variants: [] },
			};
		});
		await store.refresh_prices();
		assert.equal(store.items.length, 1);
		assert.equal(store.display_items[0].sale_price, null);
		assert.equal(store.display_items[0].default_price, null);
		assert.equal(store.display_items[0].available, false);
	});
}

test('removing a wishlist entry during refresh cannot bring it back', async () => {
	let finish;
	const store = wishlist(
		() =>
			new Promise((resolve) => {
				finish = resolve;
			}),
	);
	const refresh = store.refresh_prices();
	store.remove(store.items[0]);
	finish({
		data: { price: 300, currency: 'AED', available: true, variants: [] },
	});
	await refresh;
	assert.equal(store.items.length, 0);
	assert.equal(store.display_items.length, 0);
});

test('market prices are kept off persisted entries to avoid storage event loops', async () => {
	const store = wishlist(async () => ({
		data: { price: 300, currency: 'AED', available: true, variants: [] },
	}));
	await store.refresh_prices();
	assert.equal(store.items[0].sale_price, 80);
	assert.equal(store.display_items[0].sale_price, 300);
});
