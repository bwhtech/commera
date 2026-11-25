import { test } from '@playwright/test';

export const RUN_ID =
	process.env.COMMERA_RUN_ID ||
	Math.random().toString(36).slice(2, 8).toUpperCase();
export const PREFIX = `E2E-${RUN_ID}`;

export function e2eName(label: string) {
	return `${PREFIX}-${label}`;
}

type Cleanup = () => Promise<unknown>;

export function useCleanup() {
	const cleanups: Cleanup[] = [];
	test.afterAll(async () => {
		const failures: string[] = [];
		for (const cleanup of cleanups.reverse()) {
			await cleanup().catch((error: Error) => failures.push(error.message));
		}
		if (failures.length)
			console.error(`cleanup failed:\n${failures.join('\n')}`);
	});
	return (cleanup: Cleanup) => {
		cleanups.push(cleanup);
	};
}
