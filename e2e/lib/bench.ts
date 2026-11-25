import { execFileSync } from 'node:child_process';
import { BENCH, SITE } from './env';

export function bench<T = unknown>(
	helper: string,
	kwargs: Record<string, unknown> = {},
): T | null {
	const args = [
		'--site',
		SITE,
		'execute',
		`commera.tests.e2e_support.${helper}`,
		'--kwargs',
		JSON.stringify(kwargs),
	];
	let output: string;
	try {
		output = execFileSync('bench', args, {
			cwd: BENCH,
			encoding: 'utf8',
			stdio: ['ignore', 'pipe', 'pipe'],
		});
	} catch (error) {
		const { stdout = '', stderr = '' } = error as {
			stdout?: string;
			stderr?: string;
		};
		const lines = `${stdout}\n${stderr}`.trim().split('\n');
		const cause = lines.find((line) => /^[\w.]+(Error|Exception): /.test(line));
		throw new Error(
			`bench ${helper} failed: ${cause || lines.slice(-5).join('\n')}`,
		);
	}
	const lastLine = output.trim().split('\n').pop();
	if (!lastLine) return null;
	try {
		return JSON.parse(lastLine) as T;
	} catch {
		return lastLine as T;
	}
}

export function getSignupCode(email: string, purpose?: string) {
	return bench<number>('get_signup_code', { email, purpose });
}

export function markPaymentPaid(referenceId: string) {
	return bench<string>('mark_payment_paid', { reference_id: referenceId });
}
