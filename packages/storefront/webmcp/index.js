import { StorefrontError } from '../request.js';
import { checkout_tools } from './checkout_tools.js';
import { storefront_tools } from './storefront_tools.js';

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
