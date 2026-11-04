export function select_variant(product, selected_options = {}) {
	const variants = product?.variants ?? [];
	if (variants.length === 1) {
		return variants[0];
	}
	const size_option = product.options.find(
		(option) => !option.values.some((value) => value.handle),
	);
	const size = size_option && selected_options[size_option.name];
	return variants.find((variant) => variant.title === size) ?? null;
}
