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

export async function set_lines(lines, revision) {
	return save_cart('cart.set_lines', { lines, revision });
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

// Every write answers with the whole cart, and the page shows the last one announced. Writes run one after
// another, so a slower, older reply can never announce itself over a newer cart.
let last_write = Promise.resolve();

async function save_cart(method, params) {
	const write = last_write.then(() => post(method, params));
	last_write = write.catch(() => {});
	const cart = await write;
	globalThis.dispatchEvent(
		new CustomEvent('commera:cart-updated', { detail: cart }),
	);
	return cart;
}
