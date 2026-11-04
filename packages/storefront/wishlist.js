import { get as get_request, post } from './request.js';

export async function get() {
	return get_request('wishlist.get_wishlist');
}

export async function add(product) {
	return post('wishlist.add_to_wishlist', { product });
}

export async function remove(product) {
	return post('wishlist.remove_from_wishlist', { product });
}
