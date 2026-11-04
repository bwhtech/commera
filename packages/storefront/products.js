import { get as get_request } from './request.js';

export async function get_list({
	brands,
	colors,
	sizes,
	on_sale,
	...filters
} = {}) {
	return get_request('products.get_products', {
		...filters,
		brands: join_values(brands),
		colors: join_values(colors),
		sizes: join_values(sizes),
		on_sale: on_sale ? 1 : undefined,
	});
}

export async function get(handle) {
	return get_request('products.get_product', { handle });
}

function join_values(values) {
	return Array.isArray(values) ? values.join(',') || undefined : values;
}
