import type { APIRequestContext, Browser } from '@playwright/test';
import { ADMIN_STATE, BASE, MERCHANT_STATE } from './env';

export type Role = 'admin' | 'merchant' | 'guest';

const STATES: Record<Role, string | undefined> = {
	admin: ADMIN_STATE,
	merchant: MERCHANT_STATE,
	guest: undefined,
};

export async function login(
	request: APIRequestContext,
	email: string,
	password: string,
) {
	const response = await request.post(`${BASE}/api/method/login`, {
		data: { usr: email, pwd: password },
	});
	if (!response.ok()) {
		throw new Error(
			`login as ${email} failed at ${BASE}: HTTP ${response.status()}`,
		);
	}
}

export function newContext(browser: Browser, role: Role) {
	return browser.newContext({ storageState: STATES[role] });
}
