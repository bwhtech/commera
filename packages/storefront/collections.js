import { get as get_request } from './request.js';

export async function get_list() {
	return get_request('collections.get_collections');
}

export async function get(handle) {
	return get_request('collections.get_collection', { handle });
}
