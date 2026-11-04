import { StorefrontError, get } from './request.js';

export async function get_typeahead(query, limit) {
	return get('search.get_typeahead', { query, limit });
}

export async function get_recommendations(handle, limit) {
	if (!handle) {
		throw new StorefrontError('A product handle is required.');
	}
	return get('search.get_recommendations', { handle, limit });
}
