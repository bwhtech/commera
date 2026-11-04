import { get, post } from './request.js';

export async function cancel(name) {
	return post('orders.cancel_order', { name });
}

export async function get_return_options(name) {
	return get('orders.get_return_options', { name });
}

export async function request_return(name, items) {
	return post('orders.request_return', { name, items });
}

export async function get_invoice_url(name) {
	return get('orders.get_invoice_url', { name });
}

export async function get_tracking(name, key) {
	return get('orders.get_order_tracking', { name, key });
}

export async function send_order_link({ order_number, email }) {
	return post('orders.send_order_link', { order_number, email });
}
