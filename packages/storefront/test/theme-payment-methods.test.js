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
