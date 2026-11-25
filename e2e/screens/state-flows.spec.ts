import path from 'node:path';
import type { Page, Route } from '@playwright/test';
import { Api } from '../lib/api';
import { RUN_ID, e2eName, useCleanup } from '../lib/data';
import { ADMIN_STATE } from '../lib/env';
import { expect, test } from '../lib/fixtures';

const ADMIN_API = 'commera.api.admin.';
const IMPORT_FIXTURE = path.join(
	import.meta.dirname,
	'..',
	'fixtures',
	'import-two-rows.csv',
);

type RouterApp = {
	__vue_app__: {
		config: {
			globalProperties: { $router: { push(target: string): unknown } };
		};
	};
};

function exactText(label: string) {
	return new RegExp(
		`^\\s*${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`,
	);
}

function byText(page: Page, selector: string, label: string) {
	return page
		.locator(`${selector}:visible`)
		.filter({ hasText: exactText(label) })
		.first();
}

async function holdRequests(page: Page, matches: (url: string) => boolean) {
	const held: Route[] = [];
	let holding = true;
	await page.route(
		(url) => matches(url.href),
		async (route) => {
			if (holding) held.push(route);
			else await route.continue();
		},
	);
	return {
		held,
		async release() {
			holding = false;
			for (const route of held.splice(0))
				await route.continue().catch(() => {});
		},
		async stop() {
			await this.release();
			await page.unrouteAll({ behavior: 'ignoreErrors' });
		},
	};
}

async function fakeAnswers(page: Page, answers: Record<string, unknown>) {
	await page.route(
		(url) => Object.keys(answers).some((needle) => url.href.includes(needle)),
		async (route) => {
			const key = Object.keys(answers).find((needle) =>
				route.request().url().includes(needle),
			);
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ data: key ? answers[key] : {} }),
			});
		},
	);
	return () => page.unrouteAll({ behavior: 'ignoreErrors' });
}

function pushRoute(page: Page, target: string) {
	return page.evaluate((destination) => {
		(
			document.querySelector('#app') as unknown as RouterApp
		).__vue_app__.config.globalProperties.$router.push(destination);
	}, target);
}

async function findInputWithValue(page: Page, value: string) {
	await expect
		.poll(() =>
			page.evaluate((needle) => {
				for (const input of document.querySelectorAll('[data-e2e-value-box]'))
					input.removeAttribute('data-e2e-value-box');
				const match = [...document.querySelectorAll('input')].find(
					(input) => input.value === needle,
				);
				match?.setAttribute('data-e2e-value-box', '');
				return Boolean(match);
			}, value),
		)
		.toBe(true);
	return page.locator('[data-e2e-value-box]');
}

function fakeOrders(count: number) {
	return Array.from({ length: count }, (_, index) => ({
		name: e2eName(`SO-${String(index + 1).padStart(3, '0')}`),
		customer: 'E2E Shopper',
		placed_on: '2026-11-01',
		status: 'To Deliver and Bill',
		state: { key: 'to_fulfil', label: 'To fulfil' },
		payment_state: { key: 'paid', label: 'Paid' },
		total: 1000,
		currency: 'INR',
		item_count: 1,
		payment_mode: 'Online',
		deliveries: [],
	}));
}

async function fakeOrderList(page: Page, orders: () => unknown[]) {
	await page.route(
		(url) => url.href.includes('orders.get_orders'),
		(route) => {
			const query = new URL(route.request().url()).searchParams;
			const body = route.request().postDataJSON() ?? {};
			const start = Number(query.get('start') ?? body.start ?? 0);
			const pageLength = Number(
				query.get('page_length') ?? body.page_length ?? 20,
			);
			const all = orders();
			return route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({
					data: {
						orders: all.slice(start, start + pageLength),
						total: all.length,
					},
				}),
			});
		},
	);
}

function listRows(page: Page) {
	return page.locator('a[data-slot=list-row]');
}

test.describe('state flows', () => {
	test.use({ storageState: ADMIN_STATE });

	const cleanup = useCleanup();
	let api: Api;

	test.beforeAll(async ({ playwright }) => {
		const requestContext = await playwright.request.newContext({
			storageState: ADMIN_STATE,
		});
		api = new Api(requestContext);
		cleanup(() => requestContext.dispose());
	});

	test('import: a spreadsheet still uploading when the dialog is closed does not land in the reopened one', async ({
		page,
	}) => {
		await page.goto('/commera/products');
		await byText(page, 'button', 'Import').click();
		await byText(page, 'button', 'Continue').click();
		const hold = await holdRequests(page, (url) =>
			url.includes('/api/method/upload_file'),
		);
		const body = page.locator('body');
		const closeButton = page.locator(
			'[role=dialog] button[aria-label="Close"]',
		);
		try {
			await page
				.locator('input[type=file][accept=".csv,.xlsx"]')
				.setInputFiles(IMPORT_FIXTURE);
			await expect
				.poll(() => hold.held.length, { message: 'the held upload' })
				.toBeGreaterThan(0);
			await expect(
				body,
				'the upload step did not show it was reading',
			).toContainText('Reading rows');

			await expect(
				byText(page, 'button', 'Back'),
				'Back was usable while parsing',
			).toBeDisabled();

			await closeButton.click();
			await byText(page, 'button', 'Import').click();
			await hold.release();
			await page.waitForTimeout(2500);
			await expect(
				body,
				'the reopened dialog did not start fresh',
			).toContainText('Step 1 of 6');
			await byText(page, 'button', 'Continue').click();
			await expect(
				body,
				'the late upload wrote its file into the fresh dialog',
			).toContainText('Drop your spreadsheet here');
			await expect(
				body,
				'the late upload wrote its file name into the fresh dialog',
			).not.toContainText('import-two-rows.csv');
		} finally {
			await hold.stop();
			await closeButton.click({ timeout: 2000 }).catch(() => {});
		}
	});

	test('onboarding: the store name is locked while the store setup runs', async ({
		page,
	}) => {
		const settings = { doctype: 'Commera Settings', name: 'Commera Settings' };
		await page.goto('/commera/');
		const record = await api.get<Record<string, unknown>>(
			`${ADMIN_API}onboarding.get_onboarding`,
		);
		const running = { status: 'running', error: '' };
		await api.post('frappe.client.set_value', {
			...settings,
			fieldname: { onboarding_completed: 0 },
		});
		const stop = await fakeAnswers(page, {
			'onboarding.get_onboarding': { ...record, setup: running },
			'onboarding.get_setup_status': running,
		});
		try {
			await page.evaluate(() =>
				localStorage.setItem('commera:onboarding-step', '1'),
			);
			await page.goto('/commera/');
			await expect(page.locator('body')).toContainText('Your store');
			await expect(
				page.locator(
					'[data-onboarding-step=store] input[autocomplete=organization]',
				),
				'the store name could be edited while setup runs',
			).toBeDisabled();
			const categoriesDisabled = await page
				.locator('[data-onboarding-step=store] button[aria-pressed]')
				.evaluateAll((buttons) =>
					buttons.every((button) => (button as HTMLButtonElement).disabled),
				);
			expect(
				categoriesDisabled,
				'the category could be changed while setup runs',
			).toBe(true);
			await expect(
				page.locator('body'),
				'the lock is not explained',
			).toContainText('once setup finishes');
		} finally {
			await stop();
			await api.post('frappe.client.set_value', {
				...settings,
				fieldname: { onboarding_completed: 1 },
			});
			await page.evaluate(() =>
				localStorage.removeItem('commera:onboarding-step'),
			);
		}
	});

	test('orders: a page size change drops a selection the new page cannot show', async ({
		page,
	}) => {
		await fakeOrderList(page, () => fakeOrders(20));
		await page.goto('/commera/orders');
		await byText(page, 'button', 'Select').click();
		const rows = listRows(page);
		await expect(rows, 'needs fifteen orders on the first page').toHaveCount(
			20,
		);
		await rows.nth(14).click();
		await expect(page.locator('body')).toContainText('1 order selected');
		await page.locator('[aria-label="Rows per page"]').click();
		await byText(page, '[role=option]', '10 per page').click();
		await expect(rows).toHaveCount(10);
		await expect(
			page.locator('body'),
			'row 15 stayed selected after it left the page',
		).not.toContainText('1 order selected');
	});

	test('orders: a reload that moves a selected order off the page drops it from the selection', async ({
		page,
	}) => {
		let shifted = false;
		await fakeOrderList(page, () =>
			shifted ? fakeOrders(21).slice(1) : fakeOrders(20),
		);
		await page.route(
			(url) => url.href.includes('orders.fulfil_order'),
			(route) => {
				shifted = true;
				return route.fulfill({
					status: 417,
					contentType: 'application/json',
					body: JSON.stringify({
						errors: [{ type: 'ValidationError', message: 'Order is on hold' }],
					}),
				});
			},
		);
		await page.goto('/commera/orders');
		await byText(page, 'button', 'Select').click();
		await listRows(page).first().click();
		await expect(page.locator('body')).toContainText('1 order selected');

		await byText(page, 'button', 'Mark fulfilled').click();
		await expect(page.locator('body')).toContainText('failed');
		await expect(
			page.locator('body'),
			'an order no longer on the page stayed selected',
		).not.toContainText('1 order selected');
	});

	test('discount editor: no false unsaved prompt, edits are guarded, and Save and Active never overlap', async ({
		page,
	}) => {
		const discount = await api.post<{ name: string }>(
			`${ADMIN_API}discounts.save_discount`,
			{
				discount: {
					title: e2eName('Discount'),
					code: `E2E${RUN_ID}`,
					method: 'Code',
					discount_type: 'Amount Off Order',
					enabled: 1,
					value_type: 'Percentage',
					value: 5,
				},
			},
		);
		cleanup(() =>
			api
				.post(`${ADMIN_API}discounts.delete_discount`, { name: discount.name })
				.catch(() => {}),
		);
		page.on('dialog', (dialog) => dialog.accept());
		const body = page.locator('body');
		const editorUrl = `/commera/discounts/${encodeURIComponent(discount.name)}`;
		const saveRoute = (url: URL) =>
			url.href.includes('discounts.save_discount');

		await page.goto(editorUrl);
		await expect(body).toContainText('Setup');
		await pushRoute(page, '/discounts');
		await expect(page, 'leaving an untouched discount was blocked').toHaveURL(
			/\/discounts$/,
		);
		await expect(
			body,
			'an untouched discount asked about unsaved changes',
		).not.toContainText('Discard unsaved changes?');

		await page.goto(editorUrl);
		await expect(body).toContainText('Setup');
		const valueBox = await findInputWithValue(page, '5');
		await valueBox.click();
		await valueBox.pressSequentially('0');
		await pushRoute(page, '/discounts');
		await expect(body).toContainText('Discard unsaved changes?');
		await byText(page, '[role=dialog] button', 'Cancel').click();
		expect(page.url(), 'Cancel left the editor').toContain(
			`/discounts/${encodeURIComponent(discount.name)}`,
		);

		const writes: Array<string | null> = [];
		await page.route(saveRoute, async (route) => {
			writes.push(route.request().postData());
			setTimeout(() => route.continue().catch(() => {}), 800);
		});
		try {
			await byText(page, 'button', 'Save').click();
			await page
				.locator('button[role=switch]')
				.first()
				.click({ force: true })
				.catch(() => {});
			await expect(body).toContainText('Saved');
			await page.waitForTimeout(1200);
			expect(
				writes.length,
				`Save and Active overlapped: ${writes.length} writes`,
			).toBe(1);
		} finally {
			await page.unrouteAll({ behavior: 'ignoreErrors' });
		}

		const savedBox = await findInputWithValue(page, '50');
		await savedBox.click();
		await savedBox.press('Backspace');
		let release!: () => void;
		const gate = new Promise<void>((resolve) => {
			release = resolve;
		});
		await page.route(saveRoute, async (route) => {
			await gate;
			await route.continue().catch(() => {});
		});
		try {
			await page.locator('button[role=switch]').first().click();
			await page.waitForTimeout(300);
			await pushRoute(page, '/discounts');
			await expect(
				body,
				'the unsaved prompt while the switch saves',
			).toContainText('Discard unsaved changes?');
			await byText(page, '[role=dialog] button', 'Cancel').click();
		} finally {
			release();
			await page.waitForTimeout(1200);
			await page.unrouteAll({ behavior: 'ignoreErrors' });
		}

		await page.locator('button[aria-label="More actions"]').click();
		await byText(page, '[role=menuitem]', 'Delete discount').click();
		await byText(page, '[role=dialog] button', 'Delete discount').click();
		await expect(page).toHaveURL(/\/discounts$/);
		await expect(
			body,
			'a deleted discount asked about unsaved changes',
		).not.toContainText('Discard unsaved changes?');
	});

	test('reviews: two quick publish toggles both land, with no aborted error', async ({
		page,
	}) => {
		const review = (name: string) => ({
			name,
			shopper: `Shopper ${name}`,
			product: 'Demo product',
			rating: 0.8,
			review_title: `Review ${name}`,
			comment: 'Fine.',
			creation: '2026-11-01 10:00:00',
			is_published: 0,
		});
		const writes: string[] = [];
		await page.route(
			(url) =>
				url.href.includes('reviews.get_reviews') ||
				url.href.includes('reviews.set_published'),
			async (route) => {
				const request = route.request();
				if (request.url().includes('reviews.get_reviews')) {
					return route.fulfill({
						status: 200,
						contentType: 'application/json',
						body: JSON.stringify({
							data: { reviews: [review('E2E-R1'), review('E2E-R2')], total: 2 },
						}),
					});
				}
				writes.push(JSON.parse(request.postData() || '{}').name);
				setTimeout(
					() =>
						route
							.fulfill({
								status: 200,
								contentType: 'application/json',
								body: JSON.stringify({ data: {} }),
							})
							.catch(() => {}),
					600,
				);
			},
		);
		try {
			await page.goto('/commera/reviews');
			const switches = page.locator('button[role=switch]');
			await expect(
				switches,
				'the two faked reviews did not render',
			).toHaveCount(2);
			await switches.nth(0).click();
			await switches.nth(1).click();
			await page.waitForTimeout(2000);
			expect(writes, 'both toggles should reach the server, in order').toEqual([
				'E2E-R1',
				'E2E-R2',
			]);
			const checked = await switches.evaluateAll((buttons) =>
				buttons.map((button) => button.getAttribute('aria-checked')),
			);
			expect(checked, 'a toggle was reverted').toEqual(['true', 'true']);
			const toasts = (
				await page.locator('[data-sonner-toast]').allInnerTexts()
			).join(' / ');
			expect(toasts, `an abort was reported: ${toasts}`).not.toMatch(/abort/i);
		} finally {
			await page.unrouteAll({ behavior: 'ignoreErrors' });
		}
	});

	test('pages: after a failed move to another page, Save is gone and writes nothing', async ({
		page,
	}) => {
		const pageA = {
			name: 'E2E Page A',
			route: 'e2e-page-a',
			published: 0,
			content: '<p>Page A</p>',
		};
		const saves: Array<string | null> = [];
		await page.route(
			(url) =>
				url.href.includes('pages.save_page') ||
				url.href.includes('pages.get_page'),
			async (route) => {
				const request = route.request();
				if (request.url().includes('pages.save_page')) {
					saves.push(request.postData());
					return route.fulfill({
						status: 200,
						contentType: 'application/json',
						body: JSON.stringify({ data: pageA }),
					});
				}
				const asked = JSON.parse(request.postData() || '{}').name;
				if (asked === pageA.name) {
					return route.fulfill({
						status: 200,
						contentType: 'application/json',
						body: JSON.stringify({ data: pageA }),
					});
				}
				await route.fulfill({
					status: 404,
					contentType: 'application/json',
					body: JSON.stringify({
						errors: [
							{
								type: 'DoesNotExistError',
								message: 'Web Page E2E Page B not found',
							},
						],
					}),
				});
			},
		);
		try {
			await page.goto(
				`/commera/storefront/pages/${encodeURIComponent(pageA.name)}`,
			);
			await expect(
				byText(page, 'button', 'Save'),
				'page A did not offer Save',
			).toBeVisible();
			await pushRoute(page, '/storefront/pages/E2E%20Page%20B');
			await expect(page.locator('body')).toContainText(
				'Could not load this page',
			);
			await expect(
				byText(page, 'button', 'Save'),
				'Save is still offered after the failed load',
			).toHaveCount(0);
			expect(saves, 'something was saved').toEqual([]);
		} finally {
			await page.unrouteAll({ behavior: 'ignoreErrors' });
		}
	});
});
