import path from 'node:path';

export const BASE = process.env.COMMERA_BASE || 'http://e2e.localhost:8000';
export const SITE = process.env.COMMERA_SITE || new URL(BASE).hostname;
export const BENCH =
	process.env.COMMERA_BENCH ||
	path.join(process.env.HOME || '', 'frappe-bench');

export const ADMIN = {
	email: 'Administrator',
	password: process.env.COMMERA_ADMIN_PASSWORD || 'admin',
};

export const MERCHANT = {
	email: process.env.COMMERA_MERCHANT_EMAIL || 'merchant@e2e.commera.test',
	password: process.env.COMMERA_MERCHANT_PASSWORD || 'admin',
};

export const AUTH_DIR = path.join(import.meta.dirname, '..', '.auth');
export const ADMIN_STATE = path.join(AUTH_DIR, 'admin.json');
export const MERCHANT_STATE = path.join(AUTH_DIR, 'merchant.json');
