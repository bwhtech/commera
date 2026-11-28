import type { Browser, BrowserContext } from '@playwright/test';
import { Api } from './api';
import { login, newContext } from './auth';
import { bench, markPaymentPaid } from './bench';
import { e2eName } from './data';
import { type Address, SHOP, makeAddress } from './storefront';

export const SHOPPER_PASSWORD = 'E2e-shopper-pass!1';

export type Shopper = { email: string; context: BrowserContext; api: Api };

export function shopperEmail(label: string) {
	return `${e2eName(label)}@example.com`.toLowerCase();
}

export async function createShopper(adminApi: Api, label: string) {
	const email = shopperEmail(label);
	await adminApi.post('frappe.client.insert', {
		doc: {
			doctype: 'User',
			email,
			first_name: 'E2E',
			last_name: label,
			user_type: 'Website User',
			send_welcome_email: 0,
			new_password: SHOPPER_PASSWORD,
			roles: [{ role: 'Customer' }],
		},
	});
	return email;
}

export async function signInShopper(
	browser: Browser,
	email: string,
): Promise<Shopper> {
	const context = await newContext(browser, 'guest');
	await login(context.request, email, SHOPPER_PASSWORD);
	return { email, context, api: Api.for(context, `${SHOP}/cart`) };
}

type Checkout = { order_url: string };

async function prepareCheckout(
	shopper: Shopper,
	itemCode: string,
	address: Address,
) {
	const { api } = shopper;
	await api.post('commera.api.server_cart.sync_server_cart', {
		items: [{ item_code: itemCode, qty: 1, selected: 1 }],
	});
	await api.post('commera.api.payments.generate_quotation_for_cart', {
		cart: { items: [{ variant: { item_code: itemCode }, qty: 1 }] },
	});
	await api.post('commera.api.payments.update_quotation_address', {
		address: {
			is_store_pickup: false,
			billing_address: {
				is_saved: false,
				address_id: null,
				...address,
				country: 'India',
			},
			shipping_address: {
				is_saved: false,
				address_id: null,
				...address,
				country: 'India',
			},
			shipping_same_as_billing: true,
		},
	});
	const quote = await api.post<{
		options?: { title: string; amount: number }[];
		selected?: string;
	}>('commera.api.shipping.get_shipping_options');
	const options = quote.options || [];
	if (!options.length) return null;
	const cheapest = options.reduce((best, option) =>
		option.amount < best.amount ? option : best,
	);
	const deliveryOption = quote.selected || cheapest.title;
	await api.post('commera.api.shipping.set_delivery_option', {
		delivery_option: deliveryOption,
	});
	return deliveryOption;
}

async function confirmOrder(
	shopper: Shopper,
	referenceId: string,
	paymentMode?: string,
) {
	const summary = await shopper.api.post<{ order_name: string }>(
		'commera.api.payments.confirm_payment',
		{ reference_id: referenceId, payment_mode: paymentMode },
	);
	return summary.order_name;
}

export async function placeCodOrder(shopper: Shopper, itemCode: string) {
	const deliveryOption = await prepareCheckout(
		shopper,
		itemCode,
		makeAddress(shopper.email),
	);
	const checkout = await shopper.api.post<Checkout>(
		'commera.api.payments.initiate_checkout_with_mode',
		{ payment_mode: 'COD', delivery_option: deliveryOption },
	);
	const referenceId = new URL(checkout.order_url, 'http://x').searchParams.get(
		'reference_id',
	) as string;
	return confirmOrder(shopper, referenceId, 'COD');
}

export function openOnlineCheckout(args: {
	email: string;
	payment_mode: string;
	delivery_option?: string | null;
	expected_total?: number;
}) {
	const kwargs = Object.fromEntries(
		Object.entries(args).filter(
			([, value]) => value !== null && value !== undefined,
		),
	);
	return bench<{ order_url: string; reference_id: string }>(
		'open_online_checkout',
		kwargs,
	) as { order_url: string; reference_id: string };
}

export async function placePaidOrder(
	shopper: Shopper,
	itemCode: string,
	gateway: string,
) {
	const deliveryOption = await prepareCheckout(
		shopper,
		itemCode,
		makeAddress(shopper.email),
	);
	const { reference_id } = openOnlineCheckout({
		email: shopper.email,
		payment_mode: gateway,
		delivery_option: deliveryOption,
	});
	markPaymentPaid(reference_id);
	return confirmOrder(shopper, reference_id);
}

export const TEST_GATEWAY = 'Razorpay';

export function setTestGateway(adminApi: Api, enabled: boolean) {
	return adminApi.post('commera.api.admin.payments.save_payment_integration', {
		slug: 'razorpay',
		enabled: enabled ? 1 : 0,
		values: enabled
			? {
					key_id: 'rzp_test_e2e',
					key_secret: 'rzp_test_e2e_secret',
					webhook_secret: 'e2e_webhook_secret',
			  }
			: {},
	});
}
