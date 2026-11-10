// The rules of commera/localization/urls.py; test/url-cases.json holds the cases both pass.

// Browsers drop tabs and newlines anywhere in a URL, and C0 controls and spaces before it.
const IGNORED_URL_CHARACTERS = /[\t\n\r]/g;
const LAST_IGNORED_LEADING_CODE = 0x20;
const SCHEME = /^([a-z][a-z0-9+.-]*):/i;
const SCRIPT_SCHEMES = new Set(['javascript', 'data', 'vbscript']);
// A script link becomes this: a link that goes nowhere.
const INERT_LINK = '#';
// Every store served English under /en/ before the default language moved to the root.
const LEGACY_PREFIX = 'en';
const NON_PAGE_PATH_PREFIXES = [
	'/api/',
	'/app/',
	'/assets/',
	'/backups',
	'/desk/',
	'/files/',
	'/private/',
	'/socket.io/',
	'/.well-known/',
];
const NO_LOCALIZATION = {
	language: null,
	default_language: null,
	available_languages: [],
	root_prefix: '',
};

// The page's localization, read on each access: the page sets it after this module loads.
export const localization = {
	get language() {
		return get_localization().language;
	},
	get default_language() {
		return get_localization().default_language;
	},
	get available_languages() {
		return get_localization().available_languages;
	},
	get root_prefix() {
		return get_localization().root_prefix;
	},
	get market() {
		return get_localization().market ?? null;
	},
	get country() {
		return get_localization().country ?? null;
	},
};

// `path` in the current language: the default language has no prefix.
// A path that names a language moves to the current one. Other links stay as they are.
export function url(path) {
	const link = new Link(path);
	return link.is_page ? link.localize(get_localization()) : link.unchanged;
}

// `_lang` and `_country` for an API call, each only when it is not the store default.
export function get_request_params() {
	const { language, default_language, market, country } = get_localization();
	const params = {};
	if (language?.code && language.code !== default_language?.code) {
		params._lang = language.code;
	}
	// The primary market is the store itself: no market, or one marked primary.
	if (country && market && !market.is_primary) {
		params._country = country;
	}
	return params;
}

// A link as a browser reads it. Only a same-site page path gets a language prefix.
class Link {
	constructor(href) {
		this.href = href;
		this.read = strip_leading_ignored(
			String(href ?? '').replace(IGNORED_URL_CHARACTERS, ''),
		);
		this.parts = split_url(this.read);
	}

	get is_page() {
		return is_same_site(this.read) && is_page_path(this.parts.path);
	}

	get unchanged() {
		return SCRIPT_SCHEMES.has(this.parts.scheme) ? INERT_LINK : this.href;
	}

	localize({ root_prefix, ...current }) {
		const prefix = root_prefix ?? '';
		const route = clean_path(
			strip_prefix(this.parts.path, get_prefix_segments(current, prefix)),
		);
		const path = route !== '/' ? prefix + route : prefix || '/';
		const query = this.parts.query ? `?${this.parts.query}` : '';
		const fragment = this.parts.fragment ? `#${this.parts.fragment}` : '';
		return path + query + fragment;
	}
}

function get_localization() {
	return globalThis.commera_storefront_config?.localization ?? NO_LOCALIZATION;
}

// The client knows only published languages and its own prefix, never unpublished ones.
function get_prefix_segments(current, prefix) {
	const languages = [
		current.language,
		current.default_language,
		...(current.available_languages ?? []),
	];
	const segments = languages
		.filter(Boolean)
		.map((language) => language.code.toLowerCase());
	return new Set([...segments, prefix.slice(1).toLowerCase(), LEGACY_PREFIX]);
}

function strip_prefix(path, segments) {
	const [segment, rest] = split_first_segment(path);
	return segment && segments.has(segment.toLowerCase()) ? rest : path;
}

function split_first_segment(path) {
	const trimmed = (path || '/').replace(/^\/+/, '');
	const slash = trimmed.indexOf('/');
	return slash === -1
		? [trimmed, '/']
		: [trimmed.slice(0, slash), trimmed.slice(slash)];
}

// Splits like Python's urlsplit for the parts a same-site link has.
function split_url(link) {
	const scheme = SCHEME.exec(link)?.[1].toLowerCase() ?? '';
	const [rest, fragment = ''] = split_once(link, '#');
	const [path, query = ''] = split_once(rest, '?');
	return { scheme, path, query, fragment };
}

function split_once(text, separator) {
	const index = text.indexOf(separator);
	return index === -1
		? [text]
		: [text.slice(0, index), text.slice(index + separator.length)];
}

// A path with one leading slash. "//host" or "/\host" would leave the site.
function clean_path(path) {
	const trimmed = path.replace(/^ +| +$/g, '').replace(/^[/\\]+|[/\\]+$/g, '');
	return `/${trimmed}`;
}

function is_same_site(link) {
	return (
		link.startsWith('/') && !link.startsWith('//') && !link.startsWith('/\\')
	);
}

function is_page_path(path) {
	const directory = `${path.replace(/\/+$/, '')}/`;
	return !NON_PAGE_PATH_PREFIXES.some((prefix) => directory.startsWith(prefix));
}

function strip_leading_ignored(text) {
	let start = 0;
	while (
		start < text.length &&
		text.charCodeAt(start) <= LAST_IGNORED_LEADING_CODE
	) {
		start += 1;
	}
	return text.slice(start);
}
