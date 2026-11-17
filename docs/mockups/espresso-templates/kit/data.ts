import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import tokens from './tokens.json' with { type: 'json' };

export const t = {
	inkGray9: tokens.colors['ink-gray-9'].hex,
	inkGray7: tokens.colors['ink-gray-7'].hex,
	inkGray5: tokens.colors['ink-gray-5'].hex,
	inkGray3: tokens.colors['ink-gray-3'].hex,
	inkGreen6: tokens.colors['ink-green-6'].hex,
	inkWhite: tokens.colors['ink-white'].hex,
	surfaceBase: tokens.colors['surface-base'].hex,
	surfaceGray1: tokens.colors['surface-gray-1'].hex,
	surfaceGray2: tokens.colors['surface-gray-2'].hex,
	outlineGray1: tokens.colors['outline-gray-1'].hex,
	outlineGray2: tokens.colors['outline-gray-2'].hex,
	radiusTag: tokens.radius.tag,
	radiusThumb: tokens.radius.thumb,
	radiusCard: tokens.radius.card,
	font: tokens.font.family,
	fontStylesheet: tokens.font.stylesheet,
	regular: tokens.font.regular,
	medium: tokens.font.medium,
	semibold: tokens.font.semibold,
};

export type Item = {
	item_name: string;
	variant: string;
	item_code: string;
	gst_hsn_code: string;
	qty: number;
	rate: number;
	price_list_rate: number;
	image: string | null;
};

export type Address = { name: string; lines: string[] };

export type Order = {
	name: string;
	customer_first_name: string;
	customer_name: string;
	transaction_date: string;
	transaction_time: string;
	payment_method: string;
	payment_status: string;
	delivery_method: string;
	delivery_window: string;
	coupon_code?: string;
	discount_amount: number;
	charges: { description: string; amount: number }[];
	tax_label: string;
	tax_rate: number;
	customer_note?: string;
	gift_message?: string;
	shipping: Address;
	billing: Address | null;
	customer_tax_id?: string;
	contact_email: string;
	contact_mobile: string;
	order_url: string;
	items: Item[];
};

export type Brand = {
	name: string;
	legal_name: string;
	address: string;
	tax_id: string;
	state: string;
	logo: string | null;
	support_email: string;
	store_url: string;
	help_url: string;
	footer_links: { label: string; url: string }[];
};

export type Copy = {
	subject: string;
	heading: string;
	intro: string;
	closing: string;
	button: string;
};

export type Step = {
	title: string;
	date?: string;
	pending_title?: string;
	detail?: string;
	done: boolean;
};

export type Sample = {
	brand: Brand;
	order: Order;
	steps: Step[];
	progress: Record<
		'shipped' | 'out_for_delivery' | 'delayed' | 'delivered' | 'pickup',
		Step[]
	>;
	shipment: {
		carrier: string;
		tracking_number: string;
		tracking_url: string;
		shipped_on: string;
		delivered_on: string;
		return_by: string;
		delay_note?: string;
	};
	pickup: {
		store_name: string;
		address: Address;
		hours: string[];
		collect_by: string;
		directions_url: string;
	};
	payment_failure: {
		attempted_method: string;
		hold_hours: number;
		held_until: string;
		payment_url: string;
	};
	cancellation: { cancelled_on: string; reason: string; refund_days: string };
	return: {
		name: string;
		requested_on: string;
		refund_amount: number;
		refund_method: string;
		refund_days: string;
		refunded_on: string;
		return_url: string;
		next_steps: string[];
		items: { item_code: string; qty: number; reason: string }[];
	};
	invoice: {
		name: string;
		posting_date: string;
		place_of_supply: string;
		taxes: { description: string; rate: number }[];
	};
	back_in_stock: { item_code: string; product_url: string };
	sign_in: { code: string; expires_in_minutes: number };
	copy: Record<
		| 'order_confirmation'
		| 'order_cancelled'
		| 'back_in_stock'
		| 'order_link'
		| 'sign_in_code'
		| 'shipped'
		| 'out_for_delivery'
		| 'shipment_delayed'
		| 'delivered'
		| 'ready_for_pickup'
		| 'refund_issued'
		| 'return_received'
		| 'payment_failed'
		| 'owner_new_order',
		Copy
	>;
	imageBase: string;
};

const sampleFile = resolve(import.meta.dirname, 'sample.json');

export function loadSample(): Sample {
	const data = JSON.parse(readFileSync(sampleFile, 'utf8'));
	return {
		...data,
		imageBase: pathToFileURL(resolve(import.meta.dirname, '../static')).href,
	};
}

export type ImageSize = 'square' | 'card' | 'thumb';

export function imageUrl(
	imageBase: string,
	image: string | null,
	size: ImageSize,
) {
	if (!image) return null;
	return size === 'square'
		? `${imageBase}/${image}.jpg`
		: `${imageBase}/${image}-${size}.jpg`;
}

export function money(value: number) {
	return `₹${value.toLocaleString('en-IN', {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	})}`;
}

export function orderTotals(order: Order) {
	const subtotal = order.items.reduce(
		(sum, row) => sum + row.qty * row.rate,
		0,
	);
	const charges = order.charges.reduce((sum, charge) => sum + charge.amount, 0);
	const grand =
		Math.round((subtotal - order.discount_amount + charges) * 100) / 100;
	const tax =
		Math.round(((grand * order.tax_rate) / (100 + order.tax_rate)) * 100) / 100;
	return { subtotal, grand, tax };
}

export function fill(text: string, values: Record<string, string>) {
	return text.replace(/\{(\w+)\}/g, (match, key) => values[key] ?? match);
}
