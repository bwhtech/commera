import { expect, realProblems, test } from '../lib/fixtures';

const ROUTES = [
	['/', 'Your store is'],
	['/orders', 'Unfulfilled'],
	['/products', 'Add product'],
	['/collections', 'Create collection'],
	['/attributes', 'New attribute'],
	['/inventory', 'Receive stock'],
	['/inventory/adjustments', 'Reason'],
	['/pricing', 'Edit prices'],
	['/discounts', 'Create discount'],
	['/customers', 'Customer since'],
	['/reviews', 'Submitted'],
	['/analytics/revenue', 'What the store earned'],
	['/analytics/inventory', 'How much capital'],
	['/analytics/storefront', 'Who reaches the store'],
	['/storefront/theme', 'Built with sections'],
	['/storefront/navigation', 'Main navigation'],
	['/storefront/translations', 'Add language'],
	['/storefront/pages', 'Add page'],
	['/settings', 'Manage your settings'],
] as const;

test.describe('every dashboard route renders', () => {
	for (const [route, marker] of ROUTES) {
		test(route, async ({ page, problems }) => {
			await page.goto(`/commera${route}`);
			await expect(page.locator('body')).toContainText(marker);
			await page.waitForLoadState('networkidle');
			expect(realProblems(problems)).toEqual([]);
		});
	}
});
