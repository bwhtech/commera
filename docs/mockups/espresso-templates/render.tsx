import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { render } from '@react-email/render';
import type { ComponentType } from 'react';
import BackInStock from './emails/back-in-stock';
import Delivered from './emails/delivered';
import OrderCancelledClassic from './emails/order-cancelled-classic';
import OrderConfirmationClassic from './emails/order-confirmation-classic';
import OrderConfirmationLookbook from './emails/order-confirmation-lookbook';
import OrderLink from './emails/order-link';
import OwnerNewOrder from './emails/owner-new-order';
import PaymentFailed from './emails/payment-failed';
import ReadyForPickup from './emails/ready-for-pickup';
import RefundIssued from './emails/refund-issued';
import ReturnReceived from './emails/return-received';
import ShippedClassic from './emails/shipped-classic';
import ShippedLookbook from './emails/shipped-lookbook';
import SignInCode from './emails/sign-in-code';
import { type Sample } from './kit/data';

const CHROMIUM =
	'/home/frappe/.agent-browser/browsers/chrome-157.0.8103.78/chrome';
const outDir = resolve(import.meta.dirname, 'out/emails');
mkdirSync(outDir, { recursive: true });

function withoutOptionalSections(sample: Sample): Sample {
	const { customer_note, gift_message, customer_tax_id, ...order } =
		sample.order;
	return { ...sample, order: { ...order, billing: null } };
}

function withMerchantText(sample: Sample): Sample {
	const copy = {
		...sample.copy,
		order_confirmation: {
			...sample.copy.order_confirmation,
			heading: "{first_name}, it's on its way to you soon.",
			intro:
				'Our studio in Bengaluru packs every order by hand. Expect one more email when it leaves us.',
			button: 'See your order',
			closing: 'Questions? Write to us at help@verano.studio.',
		},
	};
	return { ...sample, copy };
}

function withProgress(state: keyof Sample['progress']) {
	return (sample: Sample): Sample => ({
		...sample,
		steps: sample.progress[state],
	});
}

function withOutForDelivery(sample: Sample): Sample {
	return {
		...withProgress('out_for_delivery')(sample),
		copy: { ...sample.copy, shipped: sample.copy.out_for_delivery },
	};
}

function withDelay(sample: Sample): Sample {
	return {
		...withProgress('delayed')(sample),
		copy: { ...sample.copy, shipped: sample.copy.shipment_delayed },
		shipment: {
			...sample.shipment,
			delay_note:
				'Heavy rain has slowed the courier in Bengaluru by about three days.',
		},
	};
}

const emails: {
	name: string;
	Email: ComponentType<Sample>;
	props: (sample: Sample) => Sample;
}[] = [
	{
		name: 'order-confirmation-classic',
		Email: OrderConfirmationClassic,
		props: (sample) => sample,
	},
	{
		name: 'order-confirmation-classic-minimal',
		Email: OrderConfirmationClassic,
		props: withoutOptionalSections,
	},
	{
		name: 'order-confirmation-classic-merchant-text',
		Email: OrderConfirmationClassic,
		props: withMerchantText,
	},
	{
		name: 'order-confirmation-lookbook',
		Email: OrderConfirmationLookbook,
		props: (sample) => sample,
	},
	{
		name: 'order-cancelled-classic',
		Email: OrderCancelledClassic,
		props: (sample) => sample,
	},
	{
		name: 'shipped-classic',
		Email: ShippedClassic,
		props: withProgress('shipped'),
	},
	{
		name: 'shipped-classic-out-for-delivery',
		Email: ShippedClassic,
		props: withOutForDelivery,
	},
	{ name: 'shipped-classic-delayed', Email: ShippedClassic, props: withDelay },
	{
		name: 'shipped-lookbook',
		Email: ShippedLookbook,
		props: withProgress('shipped'),
	},
	{ name: 'delivered', Email: Delivered, props: withProgress('delivered') },
	{
		name: 'ready-for-pickup',
		Email: ReadyForPickup,
		props: withProgress('pickup'),
	},
	{ name: 'refund-issued', Email: RefundIssued, props: (sample) => sample },
	{ name: 'return-received', Email: ReturnReceived, props: (sample) => sample },
	{ name: 'payment-failed', Email: PaymentFailed, props: (sample) => sample },
	{ name: 'owner-new-order', Email: OwnerNewOrder, props: (sample) => sample },
	{ name: 'back-in-stock', Email: BackInStock, props: (sample) => sample },
	{ name: 'order-link', Email: OrderLink, props: (sample) => sample },
	{ name: 'sign-in-code', Email: SignInCode, props: (sample) => sample },
];

const sampleFile = resolve(import.meta.dirname, 'kit/sample.json');

function loadSample(): Sample {
	const data = JSON.parse(readFileSync(sampleFile, 'utf8'));
	return {
		...data,
		imageBase: pathToFileURL(resolve(import.meta.dirname, 'static')).href,
	};
}

const filter = process.argv[2];
const sample = loadSample();

for (const { name, Email, props } of emails) {
	if (filter && !name.includes(filter)) continue;
	const html = await render(<Email {...props(sample)} />);
	const htmlFile = resolve(outDir, `${name}.html`);
	writeFileSync(htmlFile, html);
	execFileSync(
		CHROMIUM,
		[
			'--headless=new',
			'--disable-gpu',
			'--hide-scrollbars',
			'--allow-file-access-from-files',
			'--force-device-scale-factor=2',
			'--window-size=720,5000',
			'--virtual-time-budget=8000',
			`--screenshot=${resolve(outDir, `${name}-desktop.png`)}`,
			pathToFileURL(htmlFile).href,
		],
		{ stdio: 'ignore' },
	);
	console.log(name, html.length, 'bytes');
}
