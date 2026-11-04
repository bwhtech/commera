export function add_fake_fetch(responses = {}) {
	const calls = [];
	globalThis.fetch = async (url, options) => {
		const method = new URL(url, 'http://shop.test').pathname.split('.').pop();
		calls.push({
			url,
			method,
			options,
			body: options.body ? JSON.parse(options.body) : undefined,
		});
		const { status = 200, body = { data: null } } = responses[method] ?? {};
		return {
			ok: status < 400,
			status,
			statusText: status < 400 ? 'OK' : 'Error',
			json: async () => body,
		};
	};
	return calls;
}

export function add_fake_window() {
	const target = new EventTarget();
	const events = [];
	const assigned = [];
	target.addEventListener('commera:cart-updated', (event) =>
		events.push(event.detail),
	);
	globalThis.dispatchEvent = target.dispatchEvent.bind(target);
	globalThis.location = { assign: (path) => assigned.push(path) };
	return { events, assigned };
}
