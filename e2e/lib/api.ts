import type { APIRequestContext, BrowserContext } from '@playwright/test';
import { BASE } from './env';

type Args = Record<string, unknown>;

async function getCsrfToken(request: APIRequestContext, tokenPage: string) {
	const response = await request.get(BASE + tokenPage);
	const match = (await response.text()).match(
		/csrf_token["'\]]*\s*[:=]\s*["']([^"']+)["']/,
	);
	return match?.[1];
}

export class Api {
	private csrfToken: string | undefined;

	constructor(
		private request: APIRequestContext,
		private tokenPage = '/commera',
	) {}

	static for(context: BrowserContext, tokenPage?: string) {
		return new Api(context.request, tokenPage);
	}

	async get<T = unknown>(method: string, args: Args = {}): Promise<T> {
		const params = Object.fromEntries(
			Object.entries(args).map(([key, value]) => [
				key,
				typeof value === 'string' ? value : JSON.stringify(value),
			]),
		);
		const response = await this.request.get(`${BASE}/api/method/${method}`, {
			params,
		});
		return this.read<T>(method, response);
	}

	async post<T = unknown>(method: string, args: Args = {}): Promise<T> {
		this.csrfToken ??= await getCsrfToken(this.request, this.tokenPage);
		const headers: Record<string, string> = this.csrfToken
			? { 'X-Frappe-CSRF-Token': this.csrfToken }
			: {};
		const response = await this.request.post(`${BASE}/api/method/${method}`, {
			data: args,
			headers,
		});
		return this.read<T>(method, response);
	}

	private async read<T>(
		method: string,
		response: Awaited<ReturnType<APIRequestContext['get']>>,
	): Promise<T> {
		const body = await response.json().catch(() => ({}));
		if (!response.ok()) {
			const detail =
				body.exception || body._server_messages || response.statusText();
			throw new Error(
				`${method} returned HTTP ${response.status()}: ${detail}`,
			);
		}
		return body.message as T;
	}
}
