import { defineConfig, devices } from '@playwright/test';
import { ADMIN_STATE, BASE } from './lib/env';

const browser = {
	...devices['Desktop Chrome'],
	viewport: { width: 1440, height: 900 },
	reducedMotion: 'reduce',
	colorScheme: 'light',
} as const;

export default defineConfig({
	outputDir: 'test-results',
	fullyParallel: false,
	workers: 1,
	retries: process.env.CI ? 1 : 0,
	timeout: 60_000,
	expect: { timeout: 15_000 },
	reporter: [['list'], ['html', { open: 'never' }]],
	use: {
		baseURL: BASE,
		trace: 'on-first-retry',
		screenshot: 'only-on-failure',
	},
	projects: [
		{ name: 'setup', testDir: './lib', testMatch: /auth\.setup\.ts/ },
		{
			name: 'smoke',
			testDir: './smoke',
			dependencies: ['setup'],
			use: { ...browser, storageState: ADMIN_STATE },
		},
		{
			name: 'journeys',
			testDir: './journeys',
			dependencies: ['setup'],
			use: browser,
		},
		{
			name: 'screens',
			testDir: './screens',
			dependencies: ['setup'],
			use: browser,
		},
	],
});
