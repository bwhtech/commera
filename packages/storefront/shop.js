import { get } from './request.js';

export async function list_countries() {
	return get('shop.list_countries');
}

export async function list_pages() {
	return get('shop.list_pages');
}

export async function get_page(handle) {
	return get('shop.get_page', { handle });
}
