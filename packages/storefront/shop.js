import { get, post } from './request.js';

export async function list_countries() {
	return get('shop.list_countries');
}

// The countries of each other market, by market: `{ market, title, currency, countries }`.
// `title` labels the group: the market's name, or "Other countries" for the primary market.
export async function list_other_market_countries() {
	return get('shop.list_other_market_countries');
}

export async function list_pages() {
	return get('shop.list_pages');
}

export async function get_page(handle) {
	return get('shop.get_page', { handle });
}

export async function subscribe_to_newsletter(email) {
	return post('shop.subscribe_to_newsletter', { email });
}
