import { get } from './request.js';

export async function list_countries() {
	return get('shop.list_countries');
}
