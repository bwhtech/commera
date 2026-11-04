import { get as get_request, post } from './request.js';

export async function get() {
	return get_request('cart.get_cart');
}

export async function add_lines(lines) {
	return save_cart('cart.add_lines', { lines });
}

export async function update_lines(lines) {
	return save_cart('cart.update_lines', { lines });
}

export async function remove_lines(line_ids) {
	return save_cart('cart.remove_lines', { line_ids });
}

export async function apply_discount(code) {
	return save_cart('cart.add_discount_code', { code });
}

export async function remove_discount(code) {
	return save_cart('cart.remove_discount_code', { code });
}

export async function go_to_checkout() {
	const { path } = await post('cart.get_checkout_url');
	globalThis.location.assign(path);
}

async function save_cart(method, params) {
	const cart = await post(method, params);
	globalThis.dispatchEvent(
		new CustomEvent('commera:cart-updated', { detail: cart }),
	);
	return cart;
}
