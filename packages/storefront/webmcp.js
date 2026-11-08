import * as cart from './cart.js';
import * as checkout from './checkout.js';
import * as collections from './collections.js';
import * as products from './products.js';
import { StorefrontError } from './request.js';
import * as search from './search.js';

const READS_STORE_DATA = { readOnlyHint: true, untrustedContentHint: true };
// A write that returns store or shopper text still marks it untrusted.
const RETURNS_STORE_DATA = { untrustedContentHint: true };
const NO_INPUT = { type: 'object', properties: {} };
const HANDLE_INPUT = {
	type: 'object',
	properties: {
		handle: { type: 'string', description: 'The product handle.' },
	},
	required: ['handle'],
};

const storefront_tools = [
	{
		name: 'search_catalog',
		description:
			'Search the store for products and categories. Returns matching products with prices, availability and page URLs.',
		inputSchema: {
			type: 'object',
			properties: {
				query: { type: 'string', description: 'What the shopper looks for.' },
				limit: { type: 'integer', minimum: 1, maximum: 20 },
			},
			required: ['query'],
		},
		annotations: READS_STORE_DATA,
		async run({ query, limit }) {
			const results = await search.get_typeahead(query, limit);
			return {
				...results,
				products: results.products.map(add_product_url),
				search_url: `${get_language_root()}/products?${new URLSearchParams({
					search: query,
				})}`,
			};
		},
	},
	{
		name: 'browse_store',
		description:
			'Without a collection, list the store collections. With a collection handle, list its products, 24 per page, with optional price filters.',
		inputSchema: {
			type: 'object',
			properties: {
				collection: { type: 'string', description: 'A collection handle.' },
				min_price: { type: 'number', minimum: 0 },
				max_price: { type: 'number', minimum: 0 },
				page: { type: 'integer', minimum: 1 },
			},
		},
		annotations: READS_STORE_DATA,
		async run({ collection, min_price, max_price, page }) {
			if (!collection) {
				const list = await collections.get_list();
				return { collections: list.map(add_collection_url) };
			}
			const result = await products.get_list({
				collection,
				min_price,
				max_price,
				page,
			});
			return { ...result, products: result.products.map(add_product_url) };
		},
	},
	{
		name: 'get_product',
		description:
			'Get one product: description, images, options and variants with price and stock. Each variant id is the item_code that update_cart takes.',
		inputSchema: HANDLE_INPUT,
		annotations: READS_STORE_DATA,
		async run({ handle }) {
			return add_product_url(await products.get(handle));
		},
	},
	{
		name: 'show_product',
		description: "Open a product's page in the shopper's tab.",
		inputSchema: HANDLE_INPUT,
		annotations: {},
		async run({ handle }) {
			return navigate(get_product_url(handle));
		},
	},
	{
		name: 'get_cart',
		description:
			"Get the shopper's cart: lines, quantities, discounts and totals. The cart is null when the shopper has no cart yet; a cart can also exist with no lines. Pass its version to update_cart.",
		inputSchema: NO_INPUT,
		annotations: READS_STORE_DATA,
		async run() {
			return { cart: await cart.get() };
		},
	},
	{
		name: 'update_cart',
		description:
			'Set the cart to exactly these lines. Give a line_id to keep or change an existing line, or an item_code (a variant id) to add a new one. Existing lines left out are removed. If the cart changed since you read it, nothing changes and you get the current cart back.',
		inputSchema: {
			type: 'object',
			properties: {
				version: {
					type: ['string', 'null'],
					description:
						'The version of the cart from get_cart. Send null only when get_cart returned a null cart, not for a cart with no lines.',
				},
				lines: {
					type: 'array',
					items: {
						type: 'object',
						properties: {
							line_id: { type: 'string' },
							item_code: { type: 'string' },
							qty: { type: 'integer', minimum: 1 },
						},
						required: ['qty'],
					},
				},
			},
			required: ['version', 'lines'],
		},
		annotations: RETURNS_STORE_DATA,
		run: set_cart_lines,
	},
	{
		name: 'clear_cart',
		description: 'Remove every line from the cart.',
		inputSchema: NO_INPUT,
		annotations: RETURNS_STORE_DATA,
		async run() {
			const current = await cart.get();
			if (!current?.lines.length) {
				return { cart: current };
			}
			return {
				cart: await cart.remove_lines(
					current.lines.map((line) => line.line_id),
				),
			};
		},
	},
	{
		name: 'proceed_to_checkout',
		description: 'Take the shopper to checkout with the current cart.',
		inputSchema: NO_INPUT,
		annotations: {},
		async run() {
			const current = await cart.get();
			if (!current?.lines.length) {
				throw new StorefrontError('The cart is empty.');
			}
			await cart.go_to_checkout();
			return { navigating: true };
		},
	},
];

const checkout_tools = [
	{
		name: 'get_checkout',
		description:
			'Get the checkout: email, addresses, store pickup, shipping option and the charge summary with taxes and total. The checkout is null until the shopper saves contact and delivery details.',
		inputSchema: NO_INPUT,
		annotations: READS_STORE_DATA,
		async run() {
			return { checkout: await checkout.get() };
		},
	},
	{
		name: 'navigate_to_storefront',
		description: 'Leave checkout and return to the cart page.',
		inputSchema: NO_INPUT,
		annotations: {},
		async run() {
			return navigate(`${get_language_root()}/cart`);
		},
	},
];

export function is_checkout_page() {
	return /\/cart\/checkout\/?$/.test(globalThis.location.pathname);
}

export function get_tools() {
	return is_checkout_page() ? checkout_tools : storefront_tools;
}

export async function register_tools(
	model_context = globalThis.document?.modelContext,
) {
	if (!model_context) {
		return [];
	}
	const tools = get_tools();
	await Promise.all(
		tools.map(({ run, ...tool }) =>
			model_context.registerTool({
				...tool,
				execute: (input) => run_tool(run, input ?? {}),
			}),
		),
	);
	return tools.map((tool) => tool.name);
}

async function run_tool(run, input) {
	try {
		const data = await run(input);
		return {
			content: [{ type: 'text', text: JSON.stringify(data) }],
			structuredContent: data,
		};
	} catch (error) {
		if (!(error instanceof StorefrontError)) {
			throw error;
		}
		return { isError: true, content: [{ type: 'text', text: error.message }] };
	}
}

async function set_cart_lines({ version, lines }) {
	const current = await cart.get();
	if ((current?.version ?? null) !== version) {
		return {
			cart: current,
			changed: false,
			message: 'The cart changed since you read it. Read it again and retry.',
		};
	}
	const wanted = new Map(
		lines
			.filter((line) => line.line_id)
			.map((line) => [line.line_id, line.qty]),
	);
	const existing = current?.lines ?? [];
	const unknown = [...wanted.keys()].filter(
		(line_id) => !existing.some((line) => line.line_id === line_id),
	);
	if (unknown.length) {
		throw new StorefrontError(`The cart has no line ${unknown.join(', ')}.`);
	}
	const changes = existing
		.filter((line) => wanted.get(line.line_id) !== line.qty)
		.map((line) => ({
			line_id: line.line_id,
			qty: wanted.get(line.line_id) ?? 0,
		}));
	const additions = lines
		.filter((line) => !line.line_id)
		.map(({ item_code, qty }) => ({ item_code, qty }));

	let updated = current;
	if (changes.length) {
		updated = await cart.update_lines(changes);
	}
	if (additions.length) {
		updated = await cart.add_lines(additions);
	}
	return { cart: updated, changed: updated !== current };
}

function navigate(path) {
	globalThis.location.assign(path);
	return { navigating_to: path };
}

function get_language_root() {
	return `/${globalThis.commera_storefront_config?.language ?? 'en'}`;
}

function get_product_url(handle) {
	return `${get_language_root()}/products/${encodeURIComponent(handle)}`;
}

function add_product_url(product) {
	return { ...product, url: get_product_url(product.handle) };
}

function add_collection_url(collection) {
	const query = new URLSearchParams({ category: collection.handle });
	return { ...collection, url: `${get_language_root()}/products?${query}` };
}
