import { type Page, test as base } from '@playwright/test';

function watchPage(page: Page, problems: string[]) {
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
];

export function realProblems(problems: string[]) {
	return [...new Set(problems)].filter(
		(entry) =>
			!KNOWN_PROBLEMS.some((needle) => entry.includes(needle)) &&
			!entry.startsWith('CONSOLE: Failed to load resource'),
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
