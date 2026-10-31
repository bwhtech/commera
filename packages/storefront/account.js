import { get, post } from './request.js';

export async function get_profile() {
	return get('account.get_profile');
}

export async function update_profile({ first_name, last_name, phone }) {
	return post('account.update_profile', { first_name, last_name, phone });
}

export async function list_addresses() {
	return get('account.list_addresses');
}

export async function save_address(address) {
	return post('account.save_address', { address });
}

export async function delete_address(name) {
	return post('account.delete_address', { name });
}

export async function list_orders({ page, page_size } = {}) {
	return get('account.list_orders', { page, page_size });
}

export async function get_order(name, key) {
	return get('account.get_order', { name, key });
}
