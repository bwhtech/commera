import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const STARTER_SCRIPT = new URL(
	'../../../commera/public/themes/commera_starter/scripts/storefront.js',
	import.meta.url,
);

function make_storage() {
	const values = new Map();
	return {
		getItem: (key) => values.get(key) ?? null,
		setItem: (key, value) => values.set(key, String(value)),
		removeItem: (key) => values.delete(key),
	};
}

function make_page(storage = make_storage(), commera = {}) {
	// The script resets its busy state on a back/forward restore, so the page needs `pageshow` too.
	const context = {
		commera,
		addEventListener(name, callback) {
			context.events[name] = callback;
		},
		events: {},
		document: { addEventListener() {} },
		sessionStorage: storage,
		location: {
			assign(url) {
				context.opened = url;
			},
		},
	};
	vm.createContext(context);
	vm.runInContext(readFileSync(STARTER_SCRIPT, 'utf8'), context);
	return context;
}

const market_switches = {
	countries: { 'United Arab Emirates': 'gulf' },
	markets: {
		gulf: {
			url: '/en-ae/cart/checkout',
			prompt: '{0} is in the Gulf market. Switch to shop in AED?',
		},
	},
};

function make_checkout_form(page = make_page()) {
	return page.checkout({
		saved_addresses: ['ADDR-GULF'],
		saved_countries: { 'ADDR-GULF': 'United Arab Emirates' },
		country: 'India',
		is_guest: false,
		pickup_titles: {},
		market_switches,
	});
}

function pick_country(form, kind, country) {
	form.forms[kind].country = country;
	form.choose_country(kind, {
		target: { value: country, selectedOptions: [{ text: country }] },
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

test('the Starter checkout offers a switch for a country of another market', () => {
	const form = make_checkout_form();
	form.choices.shipping = 'new';

	pick_country(form, 'shipping', 'India');
	assert.equal(
		form.market_offer,
		null,
		'a country of the market is just picked',
	);

	pick_country(form, 'shipping', 'United Arab Emirates');
	assert.equal(
		form.market_offer.prompt,
		'United Arab Emirates is in the Gulf market. Switch to shop in AED?',
	);

	form.decline_market();
	assert.equal(form.market_offer, null);
	assert.equal(
		form.forms.shipping.country,
		'India',
		'not now puts the country back',
	);
});

test('the Starter checkout offers a switch for a saved address in another market', async () => {
	const form = make_checkout_form();
	assert.equal(form.choices.shipping, 'ADDR-GULF');

	await form.save_address();

	assert.match(form.market_offer.prompt, /Switch to shop in AED/);
	assert.equal(form.busy, false, 'nothing is saved before the shopper answers');
});

test('a market switch opens the new market and keeps the address', () => {
	const page = make_page();
	const form = make_checkout_form(page);
	form.choices.shipping = 'new';
	form.forms.shipping.address_line1 = '1 Marina Walk';
	pick_country(form, 'shipping', 'United Arab Emirates');

	form.accept_market_switch();
	assert.equal(page.opened, '/en-ae/cart/checkout');

	page.location.pathname = page.opened;
	const next = make_checkout_form(page);
	next.state = {
		is_store_pickup: false,
		shipping_address: address,
		billing_address: address,
	};
	next.restore_state();
	next.restore_market_draft();
	assert.equal(next.editing_address, true);
	assert.equal(next.choices.shipping, 'new');
	assert.equal(next.forms.shipping.address_line1, '1 Marina Walk');
	assert.equal(next.forms.shipping.country, 'United Arab Emirates');

	const later = make_checkout_form(page);
	later.restore_market_draft();
	assert.equal(
		later.forms.shipping.address_line1,
		'',
		'the draft is used once',
	);
});

test('an allowed country clears a stale market offer', () => {
	const form = make_checkout_form();
	pick_country(form, 'shipping', 'United Arab Emirates');
	pick_country(form, 'shipping', 'India');
	assert.equal(form.market_offer, null);
});

test('declining a saved address switches to a new allowed address', async () => {
	const form = make_checkout_form();
	await form.save_address();
	form.decline_market();
	assert.equal(form.choices.shipping, 'new');
	assert.equal(form.forms.shipping.country, 'India');
	assert.equal(form.offer_address_market(), false);
});

for (const reason of ['destination', 'scope', 'expired', 'auth']) {
	test(`a market draft is discarded after ${reason} changes`, () => {
		const page = make_page();
		const form = make_checkout_form(page);
		pick_country(form, 'shipping', 'United Arab Emirates');
		form.accept_market_switch();
		page.location.pathname = page.opened;
		if (reason === 'destination') page.location.pathname = '/elsewhere';
		if (reason === 'auth') page.events['commera:auth-changed']();
		if (reason === 'expired') {
			const saved = JSON.parse(
				page.sessionStorage.getItem('commera:market-switch-draft'),
			);
			saved.expires = 0;
			page.sessionStorage.setItem(
				'commera:market-switch-draft',
				JSON.stringify(saved),
			);
		}
		const next = make_checkout_form(page);
		if (reason === 'scope')
			next.switches = { ...market_switches, draft_scope: 'other' };
		next.restore_market_draft();
		assert.equal(next.forms.shipping.country, 'India');
	});
}

test('changing a saved address clears the old offer', () => {
	const form = make_checkout_form();
	assert.equal(form.offer_address_market(), true);
	form.choices.shipping = 'new';
	assert.equal(form.offer_address_market(), false);
	assert.equal(form.market_offer, null);
});

for (const field of ['billing_same', 'delivery_method']) {
	test(`changing ${field} clears an inactive billing market offer`, async () => {
		const page = make_page();
		page.commera = { checkout: { get: async () => null } };
		const form = make_checkout_form(page);
		const watchers = {};
		form.$watch = (name, callback) => {
			watchers[name] = callback;
		};
		await form.init();
		form.choices.shipping = 'new';
		form.choices.billing = 'new';
		form.billing_same = false;
		pick_country(form, 'billing', 'United Arab Emirates');
		assert.ok(form.market_offer);

		form[field] = field === 'billing_same' ? true : 'pickup';
		watchers[field]();
		assert.equal(form.market_offer, null);
		form.accept_market_switch();
		assert.equal(page.opened, undefined);
		assert.equal(form.busy, false);
	});

	test(`acceptance rechecks ${field} before switching markets`, () => {
		const page = make_page();
		const form = make_checkout_form(page);
		form.choices.shipping = 'new';
		form.choices.billing = 'new';
		form.billing_same = false;
		pick_country(form, 'billing', 'United Arab Emirates');
		form[field] = field === 'billing_same' ? true : 'pickup';

		form.accept_market_switch();
		assert.equal(form.market_offer, null);
		assert.equal(page.opened, undefined);
		assert.equal(form.busy, false);
	});
}

test('Starter refreshes methods and clears a stale selection after saving an address', async () => {
	const form = make_checkout_form(
		make_page(undefined, {
			checkout: {
				set_addresses: async () => ({ currency: 'AED' }),
				list_shipping_options: async () => ({
					options: [],
					reason: 'standard',
				}),
				list_payment_methods: async () => [
					{ id: 'Market gateway', title: 'Market gateway' },
				],
			},
		}),
	);
	// A new address in the cart's market, so no market switch is offered.
	form.choices.shipping = 'new';
	form.forms.shipping.country = 'India';
	form.payment_methods = [{ id: 'Store gateway' }];
	form.payment_method = 'Store gateway';
	await form.save_address();
	assert.equal(form.error, '');
	assert.equal(form.editing_address, false);
	assert.equal(form.state.currency, 'AED');
	assert.equal(form.payment_methods[0].id, 'Market gateway');
	assert.equal(form.payment_method, '');
});

test('the delivery recap translates the country without changing the stored value', () => {
	const form = make_checkout_form();
	form.config.country_titles = { India: 'الهند' };
	form.state = { shipping_address: { city: 'Kochi', country: 'India' } };
	assert.equal(form.address_recap, 'Kochi, الهند');
	assert.equal(form.state.shipping_address.country, 'India');
	form.state.shipping_address.country = 'Unknown country';
	assert.equal(form.address_recap, 'Kochi, Unknown country');
});

test('Starter uses the rounded server COD total', () => {
	const form = make_checkout_form();
	form.state = {
		summary: { total: 710, cash_on_delivery: { total: 715, cod_charge: 5.25 } },
	};
	form.payment_methods = [{ id: 'cod', is_cash_on_delivery: true }];
	form.payment_method = 'cod';
	form.$store = { cart: { cart: { total: 700 } } };
	assert.equal(form.total, 715);
});
