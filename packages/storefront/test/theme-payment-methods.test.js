import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const root = new URL('../../../commera/', import.meta.url);

function summer_checkout(config = {}) {
	const html = readFileSync(
		new URL('themes/summer_theme/pages/cart/checkout.html', root),
		'utf8',
	);
	const script = html
		.split('<script>')[1]
		.split('</script>')[0]
		.replace(/{{[\s\S]*?}}/g, '"translated"');
	let checkout;
	const context = {
		URL,
		window: {
			addEventListener() {},
			location: { href: 'https://shop.example/en-ae/cart/checkout' },
		},
		document: { addEventListener: (_event, callback) => callback() },
		Alpine: {
			data: (_name, factory) => {
				checkout = factory;
			},
			$persist: (value) => ({ as: () => value }),
		},
		toast() {},
		frappe_call: async () => ({
			data: {
				message: 'Saved',
				checkout_summary: { total: 300 },
				payment_methods: ['Market gateway', 'COD'],
			},
		}),
	};
	vm.runInNewContext(script, context);
	return checkout({
		is_guest: true,
		payment_gateways: ['Store gateway'],
		show_cod: true,
		...config,
	});
}

test('Summer replaces rendered methods after a market change during the guest address step', async () => {
	const form = summer_checkout();
	form.payment_mode = 'Store gateway';
	form.get_checkout_errors = () => [];
	form.get_address_payload = () => ({});
	form.$store = { cart: { flush_sync: async () => true, items: [] } };
	form.show_summary = (summary) => {
		form.summary = summary;
	};
	form.load_shipping_options = async () => {};
	await form.save_address();
	assert.equal(form.address_step, 'saved');
	assert.deepEqual(Array.from(form.config.payment_gateways), [
		'Market gateway',
	]);
	assert.equal(form.payment_mode, null);
	assert.equal(form.summary.total, 300);
	assert.equal(form.config.show_cod, true);

	form.payment_mode = 'Market gateway';
	form.set_payment_methods(['Market gateway']);
	assert.equal(form.payment_mode, 'Market gateway');
	assert.equal(form.config.show_cod, false);
});

test('theme API calls keep the default language and the market for every HTTP method', () => {
	const html = readFileSync(
		new URL('templates/includes/frappe-call-script.html', root),
		'utf8',
	);
	const helper = html
		.slice(
			html.indexOf('function with_page_localization'),
			html.indexOf('async function frappe_call'),
		)
		.replace('{{ call_localization.language.code | tojson }}', '"en"')
		.replace('{{ call_localization.country | tojson }}', '"ae"');
	const context = {
		URL,
		window: { location: { origin: 'https://shop.example' } },
	};
	vm.runInNewContext(helper, context);
	for (const method of ['POST', 'PUT']) {
		const [, body] = context.with_page_localization(
			'/api/address',
			{ address: {} },
			method,
		);
		assert.equal(body._lang, 'en');
		assert.equal(body._country, 'ae');
	}
	for (const method of ['GET', 'DELETE']) {
		const [url] = context.with_page_localization(
			'/api/cart?items=1',
			undefined,
			method,
		);
		const query = new URL(url, 'https://shop.example').searchParams;
		assert.equal(query.get('_country'), 'ae');
		assert.equal(query.get('_lang'), 'en');
		assert.equal(query.get('items'), '1');
	}
	const [, explicit] = context.with_page_localization(
		'/api/address',
		{ _country: 'SA', _lang: 'ar' },
		'POST',
	);
	assert.equal(explicit._country, 'SA');
	assert.equal(explicit._lang, 'ar');
});

for (const country of ['Saudi Arabia', undefined]) {
	test(`Summer applies validated prefill before the default: ${country}`, async () => {
		const form = summer_checkout({
			is_guest: false,
			default_country: 'United Arab Emirates',
			prefill: country ? { country, city: 'Riyadh' } : {},
		});
		form.apply_pending_discount = () => {};
		await form.init();
		assert.equal(form.billing.country, country ?? 'United Arab Emirates');
	});
}

test('Summer uses the payable inclusive cart total before the address step', () => {
	const form = summer_checkout();
	form.$store = {
		cart: {
			total: 699.95,
			saved: 0,
			discounts: [],
			is_delivery_charged: false,
			priced: {
				items_total: 699.95,
				total: 700,
				taxes: [
					{ description: 'VAT 15% (included)', amount: 91.3, included: true },
				],
			},
		},
	};
	const summary = form.get_browser_cart_summary();
	assert.equal(summary.subtotal, 699.95);
	assert.equal(summary.total, 700);
	assert.equal(summary.taxes[0].description, 'VAT 15% (included)');
	assert.equal(summary.cash_on_delivery.total, 700);
});

test('Summer shows no delivery price until the guest cart is priced', () => {
	const form = summer_checkout({ delivery_charge: 21.98 });
	const cart = {
		total: 1234.5,
		saved: 0,
		discounts: [],
		is_delivery_charged: false,
		priced: null,
	};
	form.$store = { cart };
	form.summary = form.get_browser_cart_summary();
	assert.equal(form.shipping_amount, null);
	assert.equal(form.summary.total, 1234.5);

	cart.priced = { items_total: 1234.5 };
	cart.is_delivery_charged = true;
	form.summary = form.get_browser_cart_summary();
	assert.equal(form.shipping_amount, 21.98);

	cart.is_delivery_charged = false;
	form.summary = form.get_browser_cart_summary();
	assert.equal(form.shipping_amount, 0);
});

test('legacy checkout keeps included tax in the payable total before and after address', () => {
	const html = readFileSync(
		new URL('templates/partials/checkout/body.html', root),
		'utf8',
	);
	const script = html
		.split('<script>')[1]
		.split('</script>')[0]
		.replace(/{{[\s\S]*?}}/g, '0');
	let form;
	vm.runInNewContext(script, {
		document: { addEventListener: (_event, callback) => callback() },
		Alpine: {
			data: (_name, factory) => {
				form = factory();
			},
			$persist: (value) => ({ as: () => value }),
		},
	});
	form.charge_summary = { total: 700, shipping: 0, cod_charge: 0 };
	form.delivery_charge = 0;
	form.calculate_checkout_total();
	assert.equal(form.checkout_total, 700);
	form.billing_address_filled = true;
	form.charge_summary = { total: 710, shipping: 10, cod_charge: 0 };
	form.delivery_charge = 10;
	form.calculate_checkout_total();
	assert.equal(form.checkout_total, 710);
});

test('Summer uses the rounded server COD total', () => {
	const form = summer_checkout();
	form.address_step = 'saved';
	form.payment_mode = 'COD';
	form.summary = {
		total: 710,
		cash_on_delivery: { total: 715, cod_charge: 5.25 },
	};
	assert.equal(form.active_summary.total, 715);
});

test('legacy checkout uses the rounded server COD total', () => {
	const html = readFileSync(
		new URL('templates/partials/checkout/body.html', root),
		'utf8',
	);
	const body = html.match(
		/calculate_checkout_total\(\) \{([\s\S]*?)\n {12}\},/,
	)[1];
	const calculate = new Function('COD_PAYMENT_MODE', body);
	const state = {
		payment_mode: 'COD',
		charge_summary: { total: 710, cash_on_delivery: { total: 715 } },
	};
	calculate.call(state, 'COD');
	assert.equal(state.checkout_total, 715);
	state.payment_mode = 'gateway';
	calculate.call(state, 'COD');
	assert.equal(state.checkout_total, 710);
});
