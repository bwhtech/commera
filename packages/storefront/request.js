const API_ROOT = '/api/v2/method/commera.api.storefront';
const STATUS_MESSAGES = { 403: 'Not permitted.', 404: 'Not found.' };

export class StorefrontError extends Error {
	constructor(message, { status, exc_type, cause } = {}) {
		super(message, { cause });
		this.name = 'StorefrontError';
		this.status = status;
		this.exc_type = exc_type;
	}
}

export async function get(method, params = {}) {
	const query = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== null) {
			query.set(key, typeof value === 'object' ? JSON.stringify(value) : value);
		}
	}
	const search = query.size ? `?${query}` : '';
	return request(`${API_ROOT}.${method}${search}`, { method: 'GET' });
}

export async function post(method, params = {}) {
	return request(`${API_ROOT}.${method}`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Frappe-CSRF-Token': get_csrf_token(),
		},
		body: JSON.stringify(params),
	});
}

function get_csrf_token() {
	return (
		globalThis.commera_storefront_config?.csrf_token ??
		globalThis.frappe?.csrf_token ??
		''
	);
}

async function request(url, { headers = {}, ...options }) {
	const response = await send(url, {
		...options,
		credentials: 'same-origin',
		headers: { Accept: 'application/json', ...headers },
	});
	const body = await read_json(response);
	if (body === null && response.ok) {
		throw new StorefrontError('The store sent an unexpected response.', {
			status: response.status,
		});
	}
	const error = body?.errors?.[0];
	if (!response.ok || error) {
		throw new StorefrontError(get_error_message(body ?? {}, response), {
			status: response.status,
			exc_type: error?.type,
		});
	}
	return body.data ?? null;
}

async function send(url, options) {
	try {
		return await fetch(url, options);
	} catch (error) {
		throw new StorefrontError('Could not reach the store.', {
			status: 0,
			cause: error,
		});
	}
}

async function read_json(response) {
	try {
		return await response.json();
	} catch {
		return null;
	}
}

function get_error_message(body, response) {
	const error = body.errors?.[0] ?? {};
	return strip_html(
		error.message ||
			body.messages?.[0]?.message ||
			error.exception?.trim().split('\n').pop() ||
			STATUS_MESSAGES[response.status] ||
			response.statusText ||
			'Request failed',
	);
}

function strip_html(text) {
	return String(text)
		.replace(/<[^>]*>/g, '')
		.trim();
}
