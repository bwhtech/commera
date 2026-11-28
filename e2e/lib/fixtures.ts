import { type Page, test as base } from '@playwright/test';

export function watchPage(page: Page, problems: string[]) {
	page.on('console', (message) => {
		if (message.type() === 'error') problems.push(`CONSOLE: ${message.text()}`);
	});
	page.on('pageerror', (error) => problems.push(`PAGEERROR: ${error.message}`));
	page.on('requestfailed', (request) => {
		problems.push(`REQFAIL: ${request.url()} ${request.failure()?.errorText}`);
	});
	page.on('response', (response) => {
		if (response.status() >= 400)
			problems.push(`HTTP ${response.status()}: ${response.url()}`);
	});
}

const KNOWN_PROBLEMS = [
	'favicon',
	'summer_theme/images/shap.svg', // https://github.com/bwhtech/commera/issues/605
	/programming error:\s+AbortError: signal is aborted without reason/, // https://github.com/bwhtech/commera/issues/610
];

export function realProblems(problems: string[]) {
	return [...new Set(problems)].filter(
		(entry) =>
			!KNOWN_PROBLEMS.some((needle) =>
				typeof needle === 'string'
					? entry.includes(needle)
					: needle.test(entry),
			) && !entry.startsWith('CONSOLE: Failed to load resource'),
	);
}

export const test = base.extend<{ problems: string[] }>({
	problems: async ({ page }, use) => {
		const problems: string[] = [];
		watchPage(page, problems);
		await use(problems);
	},
});

export { expect } from '@playwright/test';
