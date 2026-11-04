import { post } from './request.js';

export async function send_login_code(email) {
	return post('auth.send_login_code', { email });
}

export async function log_in({ email, code }) {
	return change_session('auth.log_in', { email, code });
}

export async function send_signup_code({ email, first_name, last_name }) {
	return post('auth.send_signup_code', { email, first_name, last_name });
}

export async function sign_up({ email, first_name, last_name, code }) {
	return change_session('auth.sign_up', {
		email,
		first_name,
		last_name,
		code,
	});
}

export async function log_out() {
	return change_session('auth.log_out');
}

async function change_session(method, params) {
	const profile = (await post(method, params)) ?? null;
	globalThis.dispatchEvent(
		new CustomEvent('commera:auth-changed', { detail: profile }),
	);
	return profile;
}
