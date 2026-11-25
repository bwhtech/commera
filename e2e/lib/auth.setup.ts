import { test as setup } from '@playwright/test';
import { login } from './auth';
import { ADMIN, ADMIN_STATE, MERCHANT, MERCHANT_STATE } from './env';

for (const [user, state] of [
	[ADMIN, ADMIN_STATE],
	[MERCHANT, MERCHANT_STATE],
] as const) {
	setup(`sign in as ${user.email}`, async ({ playwright }) => {
		const request = await playwright.request.newContext();
		await login(request, user.email, user.password);
		await request.storageState({ path: state });
		await request.dispose();
	});
}
