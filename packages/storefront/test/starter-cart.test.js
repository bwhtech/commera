import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const STARTER_SCRIPT = new URL(
	'../../../commera/public/themes/commera_starter/scripts/storefront.js',
	import.meta.url,
);

// Runs the Starter script and its alpine:init, and returns what it registers.
function load_starter() {
	const stores = {};
	const listeners = {};
	const context = {
		addEventListener() {},
		document: {
			addEventListener(name, listener) {
				listeners[name] = listener;
			},
		},
		Alpine: {
			store(name, store) {
				stores[name] = store;
			},
			data() {},
		},
	};
	vm.createContext(context);
	vm.runInContext(readFileSync(STARTER_SCRIPT, 'utf8'), context);
	listeners['alpine:init']();
	return { context, cart: stores.cart };
}

test('a cart with a line the market does not price is flagged', () => {
	const { cart } = load_starter();
	cart.cart = { lines: [{ available: true }, { available: true }] };
	assert.equal(cart.has_unavailable, false);
	cart.cart = { lines: [{ available: true }, { available: false }] };
	assert.equal(cart.has_unavailable, true);
	cart.cart = null;
	assert.equal(cart.has_unavailable, false);
});

test('a code a market switch removed is a notice, not a chip', () => {
	const { context } = load_starter();
	const summary = context.order_summary();
	const codes = [
		{ code: 'GULF10', applied: true, removed: false },
		{ code: 'INDIA20', applied: false, removed: true, reason: 'Not here.' },
	];
	summary.$store = { cart: { cart: { discount_codes: codes } } };
	assert.deepEqual(
		summary.discount_codes.map((code) => code.code),
		['GULF10'],
	);
	assert.deepEqual(
		summary.removed_codes.map((code) => code.code),
		['INDIA20'],
	);
});
