import type { Page } from '@playwright/test';
import { Api } from '../lib/api';
import { e2eName, useCleanup } from '../lib/data';
import { ADMIN_STATE } from '../lib/env';
import { expect, realProblems, test } from '../lib/fixtures';

const ADMIN_API = 'commera.api.admin.';

test.describe('ops', () => {
	test.use({ storageState: ADMIN_STATE });

	async function adminGet<T>(
		page: Page,
		method: string,
		args: Record<string, unknown> = {},
	) {
		return Api.for(page.context()).get<T>(`${ADMIN_API}${method}`, args);
	}

	const cleanup = useCleanup();
	let api: Api;

	test.beforeAll(async ({ playwright }) => {
		const requestContext = await playwright.request.newContext({
			storageState: ADMIN_STATE,
		});
		api = new Api(requestContext);
		cleanup(() => requestContext.dispose());

		const customer = await api.post<{ name: string }>('frappe.client.insert', {
			doc: {
				doctype: 'Customer',
				customer_name: e2eName('Customer'),
				customer_type: 'Individual',
			},
		});
		cleanup(() =>
			api.post('frappe.client.delete', {
				doctype: 'Customer',
				name: customer.name,
			}),
		);
	});

	test('customers list opens a customer', async ({ page, problems }) => {
		await page.goto('/commera/customers');
		const { customers } = await adminGet<{
			customers: Array<{ id: string; name: string }>;
		}>(page, 'customers.get_customers', { page_length: 20 });
		expect(customers.length, 'the store has no customers').toBeGreaterThan(0);
		await expect(
			page.locator('body'),
			'the first customer is not in the list',
		).toContainText(customers[0].name);

		await page.goto(
			`/commera/customers/${encodeURIComponent(customers[0].id)}`,
		);
		await expect(
			page.locator('body'),
			'the customer detail did not render the customer',
		).toContainText(customers[0].name);
		expect(
			realProblems(problems),
			'the customer screens reported browser problems',
		).toEqual([]);
	});

	test('list search boxes show their search icon', async ({ page }) => {
		const missing: string[] = [];
		for (const route of [
			'/orders',
			'/products',
			'/customers',
			'/inventory',
			'/reviews',
		]) {
			await page.goto(`/commera${route}`);
			await expect(
				page.locator('input[placeholder^="Search"]').first(),
			).toBeVisible();
			const shown = await page.evaluate(() => {
				const icon = document
					.querySelector('input[placeholder^="Search"]')
					?.parentElement?.querySelector('.lucide-search');
				return Boolean(icon?.getBoundingClientRect().width);
			});
			if (!shown) missing.push(route);
		}
		expect(missing, 'search boxes without their icon').toEqual([]);
	});

	test('revenue by-month table fills its card', async ({ page }) => {
		await page.setViewportSize({ width: 1440, height: 900 });
		await page.goto('/commera/analytics/revenue');
		await expect(
			page.locator('h2').filter({ hasText: /^\s*By month\s*$/ }),
			'no By month table on the revenue report',
		).toBeVisible();
		const gap = await page.evaluate(() => {
			const heading = [...document.querySelectorAll('h2')].find(
				(node) => node.innerText.trim() === 'By month',
			);
			const section = heading?.closest('section');
			const lastColumn = [...(section?.querySelectorAll('*') ?? [])].find(
				(node) =>
					node.children.length === 0 &&
					(node as HTMLElement).innerText?.trim() === 'Net',
			);
			let cell: Element | null | undefined = lastColumn;
			while (
				cell?.parentElement &&
				getComputedStyle(cell.parentElement).display !== 'grid'
			) {
				cell = cell.parentElement;
			}
			if (!section || !cell?.parentElement) return null;
			return (
				section.getBoundingClientRect().right -
				cell.getBoundingClientRect().right
			);
		});
		if (gap === null)
			throw new Error('no By month table on the revenue report');
		expect(
			gap,
			`the table stops ${Math.round(gap)}px short of its card's edge`,
		).toBeLessThan(48);
	});

	test('inventory and pricing lists render their rows', async ({
		page,
		problems,
	}) => {
		await page.goto('/commera/inventory');
		const { rows: stockRows } = await adminGet<{
			rows: Array<{ item_code: string }>;
		}>(page, 'inventory.get_inventory', { page_length: 5 });
		expect(stockRows.length, 'the store has no stock rows').toBeGreaterThan(0);
		await expect(
			page.locator('body'),
			'the first stock row is not on screen',
		).toContainText(stockRows[0].item_code);

		await page.goto('/commera/pricing');
		const { rows: priceRows } = await adminGet<{
			rows: Array<{ title: string }>;
		}>(page, 'catalog.get_pricing_rows', { page_length: 5 });
		expect(
			priceRows.length,
			'the store has no priceable items',
		).toBeGreaterThan(0);
		await expect(
			page.locator('body'),
			'the first price row is not on screen',
		).toContainText(priceRows[0].title);
		expect(
			realProblems(problems),
			'the inventory or pricing screens reported browser problems',
		).toEqual([]);
	});
});
