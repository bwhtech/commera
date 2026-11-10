import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const STARTER_SCRIPT = new URL(
	'../../../commera/public/themes/commera_starter/scripts/storefront.js',
	import.meta.url,
);

function make_checkout_form() {
	// The script resets its busy state on a back/forward restore, so the page needs `pageshow` too.
	const context = {
		addEventListener() {},
		document: { addEventListener() {} },
	};
	vm.createContext(context);
	vm.runInContext(readFileSync(STARTER_SCRIPT, 'utf8'), context);
	return context.checkout({
		saved_addresses: [],
		country: 'India',
		is_guest: false,
		pickup_titles: {},
	});
}

const address = {
	name: 'ADDR-1',
	address_line1: '1 MG Road',
	city: 'Pune',
	country: 'India',
};

test('the Starter checkout follows a change between pickup and delivery', () => {
	const form = make_checkout_form();

	form.state = { is_store_pickup: true, store: 'Store - CO' };
	form.restore_state();
	assert.equal(form.delivery_method, 'pickup');
	assert.equal(form.pickup_location, 'Store - CO');

	form.state = {
		is_store_pickup: false,
		shipping_address: address,
		billing_address: address,
	};
	form.restore_state();
	assert.equal(form.delivery_method, 'ship');
	assert.equal(form.forms.shipping.address_line1, '1 MG Road');
	assert.equal(form.editing_address, false);
});

test('the Starter checkout shows its skeleton only while a cart with lines loads', () => {
	const form = make_checkout_form();
	const cart = { status: 'loading', count: 0 };
	form.$store = { cart };
	assert.equal(form.is_loading, true);

	Object.assign(cart, { status: 'ready', count: 2 });
	assert.equal(form.is_loading, true);

	form.ready = true;
	assert.equal(form.is_loading, false);

	form.ready = false;
	cart.count = 0;
	assert.equal(form.is_loading, false, 'an empty cart shows its empty state');

	Object.assign(cart, { status: 'failed', count: 2 });
	assert.equal(form.is_loading, false, 'a failed cart shows its retry state');

	cart.status = 'loading';
	form.sign_in_required = true;
	assert.equal(
		form.is_loading,
		false,
		'a guest without access is asked to sign in',
	);
});
