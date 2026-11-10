// UI strings in the page's language. Record content, such as product titles, comes translated
// from the server, so the dictionary holds Frappe's strings and the merchant's overrides only.
const ENDPOINT =
	'/api/v2/method/commera.api.storefront.translations.get_translations';
const PLACEHOLDER = /\{(\d+)\}/g;

let dictionary = { messages: {} };
let loaded = { url: null, promise: Promise.resolve() };

// `text` in the page's language. `{0}`, `{1}` take `args`, as in Frappe's __().
export function t(text, ...args) {
	const source = String(text ?? '');
	return format(dictionary.messages[source] || source, args);
}

// Fetches the page language's dictionary once. A page that needs none fetches nothing.
export function load_translations() {
	const url = get_dictionary_url();
	if (url !== loaded.url) {
		dictionary.messages = {};
		loaded = { url, promise: url ? fetch_messages(url) : Promise.resolve() };
	}
	return loaded.promise;
}

// Pass Alpine.reactive: bindings that call t() render again when the dictionary arrives.
export function make_translations_reactive(reactive) {
	dictionary = reactive(dictionary);
}

// The server sets the version only when the language has strings to translate.
function get_dictionary_url() {
	const config = globalThis.commera_storefront_config ?? {};
	const language = config.localization?.language?.code;
	if (!language || !config.translations_version) {
		return null;
	}
	const query = new URLSearchParams({
		lang: language,
		v: config.translations_version,
	});
	return `${ENDPOINT}?${query}`;
}

async function fetch_messages(url) {
	try {
		const response = await fetch(url, {
			credentials: 'same-origin',
			headers: { Accept: 'application/json' },
		});
		const body = response.ok ? await response.json() : null;
		if (loaded.url === url) {
			dictionary.messages = body?.data ?? {};
		}
	} catch {
		// t() keeps returning the source text.
	}
}

function format(message, args) {
	return message.replace(PLACEHOLDER, (match, index) =>
		args[index] === undefined ? match : String(args[index]),
	);
}
