import { url } from '../localization.js';
import * as shop from '../shop.js';
import { NO_INPUT, READS_STORE_DATA } from './shared.js';

export const page_tools = [
	{
		name: 'list_store_pages',
		description:
			"List the store's information pages, such as shipping, returns, privacy, FAQ and contact. Read one with get_store_page.",
		inputSchema: NO_INPUT,
		annotations: READS_STORE_DATA,
		async run() {
			const pages = await shop.list_pages();
			return { pages: pages.map(add_page_url) };
		},
	},
	{
		name: 'get_store_page',
		description:
			"Read one of the store's information pages as HTML. Use it to answer questions about the store's policies.",
		inputSchema: {
			type: 'object',
			properties: {
				handle: {
					type: 'string',
					description: 'The page handle from list_store_pages.',
				},
			},
			required: ['handle'],
		},
		annotations: READS_STORE_DATA,
		async run({ handle }) {
			return add_page_url(await shop.get_page(handle));
		},
	},
];

function add_page_url(page) {
	return {
		...page,
		url: url(`/page/${encodeURIComponent(page.handle)}`),
	};
}
