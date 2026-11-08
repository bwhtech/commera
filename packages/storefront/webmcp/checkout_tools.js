import * as checkout from '../checkout.js';
import { money_text } from '../format.js';
import { StorefrontError } from '../request.js';
import {
	NO_INPUT,
	READS_STORE_DATA,
	RETURNS_STORE_DATA,
	get_language_root,
	navigate,
} from './shared.js';

const ADDRESS_INPUT = {
	anyOf: [
		{ type: 'string', description: 'The name of a saved address.' },
		{
			type: 'object',
			properties: {
				first_name: { type: 'string' },
				last_name: { type: 'string' },
				address_line1: { type: 'string' },
				address_line2: { type: 'string' },
				city: { type: 'string' },
				state: { type: 'string' },
				pincode: { type: 'string' },
				country: { type: 'string' },
				phone: { type: 'string' },
			},
			required: ['first_name', 'address_line1', 'city', 'pincode', 'country'],
		},
	],
};

export const checkout_tools = [
	{
		name: 'get_checkout',
		description:
			'Get the checkout and its choices: email, addresses, store pickup, shipping option, the charge summary with taxes and total, and the shipping options, pickup locations and payment methods to choose from. The checkout is null until the shopper saves contact and delivery details.',
		inputSchema: NO_INPUT,
		annotations: READS_STORE_DATA,
		async run() {
			return get_checkout_view(await checkout.get());
		},
	},
	{
		name: 'update_checkout',
		description:
			'Set how the order is delivered. Send a shipping_address (and a billing_address if it differs) or a pickup_location id. Then, or later, send a shipping_option id from get_checkout. Guests must send an email with the address or pickup location.',
		inputSchema: {
			type: 'object',
			properties: {
				email: { type: 'string' },
				shipping_address: ADDRESS_INPUT,
				billing_address: ADDRESS_INPUT,
				pickup_location: { type: 'string' },
				shipping_option: { type: 'string' },
			},
		},
		annotations: RETURNS_STORE_DATA,
		run: update_checkout,
	},
	{
		name: 'complete_checkout',
		description:
			'Place the order with the current checkout. The buyer first sees the items, delivery, payment method and total in a dialog and must confirm. If the checkout changes before payment starts, nothing happens. Cash on delivery places the order; other methods open the payment page, where the buyer pays.',
		inputSchema: {
			type: 'object',
			properties: {
				payment_method: {
					type: 'string',
					description: 'A payment method id from get_checkout.',
				},
			},
			required: ['payment_method'],
		},
		annotations: { consequentialHint: true },
		run: complete_checkout,
	},
	{
		name: 'navigate_to_storefront',
		description: 'Leave checkout and return to the cart page.',
		inputSchema: NO_INPUT,
		annotations: {},
		async run() {
			return navigate(`${get_language_root()}/cart`);
		},
	},
];

async function get_checkout_view(state) {
	const [shipping, pickup_locations, payment_methods] = await Promise.all([
		state?.is_store_pickup
			? { options: [], reason: 'store_pickup' }
			: checkout.list_shipping_options(),
		checkout.list_pickup_locations(),
		checkout.list_payment_methods(),
	]);
	return {
		checkout: state,
		shipping_options: shipping.options,
		shipping_options_reason: shipping.reason ?? null,
		pickup_locations,
		payment_methods,
	};
}

async function update_checkout(input) {
	let state = await save_delivery(input);
	if (state) {
		show_checkout(state);
	}
	if (input.shipping_option) {
		state = await save_shipping_option(input.shipping_option, Boolean(state));
	}
	if (!state) {
		throw new StorefrontError(
			'Send a shipping address, a pickup location or a shipping option.',
		);
	}
	return get_checkout_view(state);
}

async function save_shipping_option(option_id, has_saved_delivery) {
	try {
		const state = await checkout.set_shipping_option(option_id);
		show_checkout(state);
		return state;
	} catch (error) {
		if (!(has_saved_delivery && error instanceof StorefrontError)) {
			throw error;
		}
		throw new StorefrontError(
			`Saved the delivery details, but not the shipping option: ${error.message}`,
			{ status: error.status, exc_type: error.exc_type, cause: error },
		);
	}
}

// Each saved step shows on the checkout page at once, even when a later step fails.
function show_checkout(state) {
	globalThis.dispatchEvent(
		new CustomEvent('commera:checkout-updated', { detail: state }),
	);
}

async function save_delivery({
	email,
	shipping_address,
	billing_address,
	pickup_location,
}) {
	if (pickup_location && (shipping_address || billing_address)) {
		throw new StorefrontError(
			'Send an address or a pickup location, not both.',
		);
	}
	if (pickup_location) {
		return checkout.set_store_pickup({ warehouse: pickup_location, email });
	}
	if (shipping_address) {
		return checkout.set_addresses({
			billing_address: billing_address ?? shipping_address,
			shipping_address: billing_address ? shipping_address : undefined,
			email,
		});
	}
	if (billing_address || email) {
		throw new StorefrontError(
			'Send a billing address or email together with a shipping address.',
		);
	}
	return null;
}

async function complete_checkout({ payment_method }) {
	const [state, methods] = await Promise.all([
		checkout.get(),
		checkout.list_payment_methods(),
	]);
	if (!state) {
		throw new StorefrontError(
			'Save the delivery details with update_checkout first.',
		);
	}
	const method = methods.find((method) => method.id === payment_method);
	if (!method) {
		throw new StorefrontError(
			`The store has no payment method ${payment_method}.`,
		);
	}
	const { total } = method.is_cash_on_delivery
		? state.summary.cash_on_delivery
		: state.summary;
	if (!globalThis.confirm(get_order_review(state, method, total))) {
		throw new StorefrontError('The buyer did not confirm the order.');
	}
	const session = await checkout.start_payment({
		payment_method,
		expected_total: total,
		expected_version: state.version,
	});
	return navigate(session.redirect_url);
}

// Built from the checkout whose version is paid, not from what the agent sent.
function get_order_review(state, method, total) {
	return [
		'Place this order?',
		'',
		...state.items.map((item) => `${item.qty} × ${item.title}`),
		'',
		get_delivery_text(state),
		...(state.email ? [`Email: ${state.email}`] : []),
		`Payment: ${method.title}`,
		`Total: ${money_text(total, state.currency)}`,
	].join('\n');
}

function get_delivery_text(state) {
	if (state.is_store_pickup) {
		return `Pick up at: ${state.store}`;
	}
	const address = state.shipping_address ?? {};
	const lines = [
		address.address_line1,
		address.address_line2,
		address.city,
		address.state,
		address.pincode,
		address.country,
	];
	return `Deliver to: ${lines.filter(Boolean).join(', ')}`;
}
