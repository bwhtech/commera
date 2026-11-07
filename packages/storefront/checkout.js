import { get as get_request, post } from './request.js';

export async function get() {
	return get_request('checkout.get');
}

export async function refresh() {
	return post('checkout.refresh');
}

export async function set_addresses({
	billing_address,
	shipping_address,
	email,
}) {
	return post('checkout.set_addresses', {
		billing_address,
		shipping_address,
		email,
	});
}

export async function list_pickup_locations() {
	return get_request('checkout.list_pickup_locations');
}

export async function set_store_pickup({ warehouse, email }) {
	return post('checkout.set_store_pickup', { warehouse, email });
}

export async function list_shipping_options() {
	return get_request('checkout.list_shipping_options');
}

export async function set_shipping_option(option_id) {
	return post('checkout.set_shipping_option', { option_id });
}

export async function list_payment_methods() {
	return get_request('checkout.list_payment_methods');
}

export async function start_payment({ payment_method, expected_total }) {
	return post('checkout.start_payment', { payment_method, expected_total });
}

export async function complete(reference_id) {
	return post('checkout.complete', { reference_id });
}
