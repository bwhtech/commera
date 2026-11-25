import { createHash } from 'node:crypto';
import type { BrowserContext, Page } from '@playwright/test';
import { Api } from '../lib/api';
import { newContext } from '../lib/auth';
import { markPaymentPaid } from '../lib/bench';
import { PREFIX, useCleanup } from '../lib/data';
import { expect, realProblems, test, watchPage } from '../lib/fixtures';
import {
	TEST_GATEWAY,
	createShopper,
	openOnlineCheckout,
	placeCodOrder,
	setTestGateway,
	shopperEmail,
	signInShopper,
} from '../lib/orders';
import {
	SHOP,
	addToCart,
	chooseDelivery,
	choosePayment,
	enterCode,
	getShownTotal,
	makeAddress,
	openCheckout,
	placeOrder,
	readConfirmation,
	saveAddress,
	sendCode,
	signIn,
	signUp,
	viewOrder,
} from '../lib/storefront';

const PRODUCT = 'solid-cutaway-shirt-gray';
const ITEMS = ['SOLID-CUTAWAY-SHIRT-GRA-L', 'CHECKERED-SLIM-SHIRT-NAV-M'];
const CODE = `${PREFIX}-TEN`.toUpperCase();

type SalesOrder = {
	name: string;
	docstatus: number;
	grand_total: number;
	rounded_total: number;
	total: number;
	contact_email: string;
	custom_ecommerce_payment_mode: string;
	custom_discount_codes?: string;
	custom_code_order_discount?: number;
	taxes: { commera_cart_charge?: string; tax_amount: number }[];
};

type EmailQueue = {
	name: string;
	message: string;
	attachments: string | null;
	recipients: { recipient: string }[];
};

test.describe('shopper buys', () => {
	test.describe.configure({ timeout: 240_000 });
	let admin: BrowserContext;
	let adminApi: Api;
	const orders: string[] = [];
	const users: string[] = [];
	const discounts: string[] = [];
	let gatewayOn = false;
	const cleanup = useCleanup();

	test.beforeAll(async ({ browser }) => {
		admin = await newContext(browser, 'admin');
		adminApi = Api.for(admin);
		cleanup(() => admin.close());
		cleanup(async () => {
			if (gatewayOn) await setTestGateway(adminApi, false);
			for (const discount of discounts)
				await adminApi
					.post('commera.api.admin.discounts.delete_discount', {
						name: discount,
					})
					.catch(() =>
						adminApi.post('frappe.client.set_value', {
							doctype: 'Commera Discount',
							name: discount,
							fieldname: 'enabled',
							value: 0,
						}),
					);
			for (const user of users)
				await adminApi.post('frappe.client.set_value', {
					doctype: 'User',
					name: user,
					fieldname: 'enabled',
					value: 0,
				});
			for (const order of orders) await removeOrder(adminApi, order);
		});
	});

	async function newShopper(label: string) {
		const email = await createShopper(adminApi, label);
		users.push(email);
		return email;
	}

	async function addDiscountCode() {
		if (discounts.length) return;
		const saved = await adminApi.post<{ name: string }>(
			'commera.api.admin.discounts.save_discount',
			{
				discount: {
					method: 'Code',
					discount_type: 'Amount Off Order',
					value_type: 'Percentage',
					value: 10,
					code: CODE,
				},
			},
		);
		discounts.push(saved.name);
	}

	async function getOrder(orderName: string) {
		return adminApi.post<SalesOrder>('frappe.client.get', {
			doctype: 'Sales Order',
			name: orderName,
		});
	}

	async function expectOrderPlaced(
		orderName: string,
		email: string,
		shownTotal: number,
	) {
		orders.push(orderName);
		const order = await getOrder(orderName);
		expect(order.contact_email).toBe(email);
		expect(order.rounded_total || order.grand_total).toBeCloseTo(shownTotal, 2);

		const settings = await adminApi.post<{
			cod_charge: number;
			cod_charge_applicable_below: number;
		}>('frappe.client.get_value', {
			doctype: 'Commera Settings',
			fieldname: ['cod_charge', 'cod_charge_applicable_below'],
		});
		const codCharge = order.taxes
			.filter((row) => row.commera_cart_charge === 'cod')
			.reduce((sum, row) => sum + row.tax_amount, 0);
		const isChargeable =
			order.custom_ecommerce_payment_mode === 'COD' &&
			order.grand_total - codCharge <= settings.cod_charge_applicable_below;
		expect(codCharge).toBe(isChargeable ? settings.cod_charge : 0);

		const events = await adminApi.post<unknown[]>('frappe.client.get_list', {
			doctype: 'Commera Event',
			filters: { event: 'order_placed', reference_name: orderName },
		});
		expect(events).toHaveLength(1);

		const email_row = await waitForEmail(adminApi, orderName);
		expect(email_row.recipients.map((row) => row.recipient)).toEqual([email]);
		expect(email_row.message).toContain(`Order ${orderName} confirmed`);
		return { order, queued: email_row };
	}

	async function checkoutWithCod(page: Page, email: string) {
		await saveAddress(page, makeAddress(email));
		await chooseDelivery(page);
		await choosePayment(page, 'Cash on Delivery');
		const total = await getShownTotal(page);
		await placeOrder(page);
		return { orderName: await readConfirmation(page), total };
	}

	test('a new shopper signs up and pays cash on delivery', async ({
		page,
		problems,
	}) => {
		const email = shopperEmail(attempt('signup'));
		await addToCart(page, PRODUCT);
		await signUp(page, email);
		users.push(email);

		await openCheckout(page);
		const { orderName, total } = await checkoutWithCod(page, email);
		await viewOrder(page, orderName);

		const { order, queued } = await expectOrderPlaced(orderName, email, total);
		expect(order.docstatus).toBe(0);
		expect(JSON.parse(queued.attachments || '[]')).toEqual([]);
		expect(realProblems(problems)).toEqual([]);
	});

	test('a guest signs in with a checkout code and pays cash on delivery', async ({
		page,
		problems,
	}) => {
		const email = shopperEmail(attempt('checkout-code'));
		await addToCart(page, PRODUCT);
		await page.goto(`${SHOP}/cart`);
		await page.getByRole('button', { name: 'Checkout' }).click();
		const dialog = page.locator('.summer-auth-panel');
		await dialog.locator('input[type="email"]:visible').fill(email);
		const sent = await sendCode(
			page,
			dialog.getByRole('button', { name: 'Send Code' }),
		);
		await expect(page.locator('.summer-auth-otp input').first()).toBeVisible();
		await enterCode(page, email, sent);
		users.push(email);
		await page.waitForURL(/\/cart\/checkout/);

		const { orderName, total } = await checkoutWithCod(page, email);
		await viewOrder(page, orderName);
		await expectOrderPlaced(orderName, email, total);
		expect(realProblems(problems)).toEqual([]);
	});

	test('a signed-in shopper pays online', async ({ browser }) => {
		await setTestGateway(adminApi, true);
		gatewayOn = true;
		const email = await newShopper(attempt('online'));
		const shopper = await signInShopper(browser, email);
		const page = await shopper.context.newPage();
		const problems: string[] = [];
		watchPage(page, problems);

		await addToCart(page, PRODUCT);
		await openCheckout(page);
		await saveAddress(page, makeAddress(email));
		await chooseDelivery(page);
		await choosePayment(page, TEST_GATEWAY);
		const total = await getShownTotal(page);

		let referenceId = '';
		await page.route(
			'**/commera.api.payments.initiate_checkout_with_mode',
			async (route) => {
				const { payment_mode, delivery_option, expected_total } = route
					.request()
					.postDataJSON();
				const checkout = openOnlineCheckout({
					email,
					payment_mode,
					delivery_option,
					expected_total,
				});
				referenceId = checkout.reference_id;
				await route.fulfill({
					json: { data: { order_url: checkout.order_url } },
				});
			},
		);
		await page.route('https://rzp.io/**', (route) =>
			route.fulfill({ contentType: 'text/html', body: '<h1>Gateway</h1>' }),
		);
		await placeOrder(page);
		await page.waitForURL(/rzp\.io/);

		markPaymentPaid(referenceId);
		await page.goto(
			`${SHOP}/account/orders/confirmation?reference_id=${encodeURIComponent(
				referenceId,
			)}`,
		);
		const orderName = await readConfirmation(page);
		await viewOrder(page, orderName);

		const { order, queued } = await expectOrderPlaced(orderName, email, total);
		expect(order.docstatus).toBe(1);
		const invoices = await adminApi.post<{ name: string }[]>(
			'frappe.client.get_list',
			{
				doctype: 'Sales Invoice',
				filters: [
					['Sales Invoice Item', 'sales_order', '=', orderName],
					['docstatus', '=', 1],
				],
			},
		);
		expect(invoices).toHaveLength(1);
		const payments = await adminApi.post<{ name: string }[]>(
			'frappe.client.get_list',
			{
				doctype: 'Payment Entry',
				filters: [
					[
						'Payment Entry Reference',
						'reference_name',
						'in',
						[orderName, invoices[0].name],
					],
					['docstatus', '=', 1],
				],
			},
		);
		expect(payments.length).toBeGreaterThan(0);
		expect(JSON.parse(queued.attachments || '[]')).toEqual([
			expect.objectContaining({
				doctype: 'Sales Invoice',
				name: invoices[0].name,
			}),
		]);
		expect(realProblems(problems)).toEqual([]);
		await shopper.context.close();
	});

	test('a discount code in a cart link reaches the order', async ({
		page,
		problems,
	}) => {
		await addDiscountCode();
		const email = shopperEmail(attempt('link'));
		await openCartLink(page, { api: adminApi }, [ITEMS[0]], { discount: CODE });
		await continueAsGuest(page);
		const { orderName, total } = await checkoutWithCod(page, email);

		const { order } = await expectOrderPlaced(orderName, email, total);
		expect(order.custom_discount_codes).toBe(CODE);
		expect(order.custom_code_order_discount).toBeCloseTo(order.total * 0.1, 2);
		expect(realProblems(problems)).toEqual([]);
	});

	test('a cart link with mode=add keeps the cart and adds its code', async ({
		page,
		problems,
	}) => {
		await addDiscountCode();
		await openCartLink(page, { api: adminApi }, [ITEMS[0]], {
			return_to: 'cart',
		});
		await openCartLink(page, { api: adminApi }, [ITEMS[1]], {
			mode: 'add',
			discount: CODE,
		});
		await expectServerCart(page, { api: adminApi }, ITEMS);
		await continueAsGuest(page);
		await expect(page.locator('tr.discount').first()).toBeVisible();
		expect(realProblems(problems)).toEqual([]);
	});

	test('a code typed into the promo box reaches the order', async ({
		page,
		problems,
	}) => {
		await addDiscountCode();
		const email = shopperEmail(attempt('promo'));
		await addToCart(page, PRODUCT);
		await page.goto(`${SHOP}/cart`);
		await page.getByRole('button', { name: 'Checkout' }).click();
		await page.getByRole('link', { name: 'Continue as Guest' }).click();
		await page.waitForURL(/\/cart\/checkout/);

		await page.getByRole('textbox', { name: 'Discount code' }).fill(CODE);
		await page.getByRole('button', { name: 'Apply', exact: true }).click();
		await expect(page.locator('tr.discount').first()).toBeVisible();

		const { orderName, total } = await checkoutWithCod(page, email);
		const { order } = await expectOrderPlaced(orderName, email, total);
		expect(order.custom_discount_codes).toBe(CODE);
		expect(realProblems(problems)).toEqual([]);
	});

	test("signing in merges the guest cart into the account's cart", async ({
		browser,
		page,
		problems,
	}) => {
		const email = await newShopper(attempt('merge'));
		const shopper = await signInShopper(browser, email);
		const saved = await shopper.context.newPage();
		await openCartLink(saved, { api: adminApi, email }, [ITEMS[0]], {
			return_to: 'cart',
		});
		await shopper.context.close();

		await openCartLink(page, { api: adminApi }, [ITEMS[1]], {
			return_to: 'cart',
		});
		await signIn(page, email);
		await page.goto(`${SHOP}/cart`);
		await expectServerCart(page, { api: adminApi, email }, ITEMS);
		expect(realProblems(problems)).toEqual([]);
	});

	test('the merchant sees the new order at the top of their orders', async ({
		browser,
	}) => {
		const email = await newShopper(attempt('merchant-view'));
		const shopper = await signInShopper(browser, email);
		const orderName = await placeCodOrder(shopper, ITEMS[0]);
		orders.push(orderName);
		await shopper.context.close();

		const merchant = await newContext(browser, 'merchant');
		const page = await merchant.newPage();
		const problems: string[] = [];
		watchPage(page, problems);
		await page.goto('/commera/orders');
		await expect(
			page.locator('a[href*="/commera/orders/"]').first(),
		).toContainText(orderName);
		await page.waitForLoadState('networkidle');
		expect(realProblems(problems)).toEqual([]);
		await merchant.close();
	});
});

function attempt(label: string) {
	return `${label}-${test.info().retry}`;
}

type CartOwner = { api: Api; email?: string };

async function openCartLink(
	page: Page,
	owner: CartOwner,
	itemCodes: string[],
	query: Record<string, string> = {},
) {
	const path = itemCodes
		.map((code) => `${encodeURIComponent(code)}:1`)
		.join(',');
	const search = new URLSearchParams(query).toString();
	await page.goto(`${SHOP}/cart/${path}${search ? `?${search}` : ''}`);
	await page.waitForURL((url) => !/\/cart\/[^/]+:\d/.test(url.pathname));
	await expectServerCart(
		page,
		owner,
		itemCodes,
		query.mode === 'add' ? 'contains' : 'equals',
	);
}

async function getCartItemCodes(page: Page, { api, email }: CartOwner) {
	let filters: Record<string, string> | null = email ? { user: email } : null;
	if (!filters) {
		const cookie = (await page.context().cookies()).find(
			(entry) => entry.name === 'commera_guest_cart',
		);
		if (!cookie) return [];
		filters = {
			cart_key: createHash('sha256').update(cookie.value).digest('hex'),
		};
	}
	const carts = await api.post<{ name: string }[]>('frappe.client.get_list', {
		doctype: 'Commera Cart',
		filters,
		order_by: 'modified desc',
		limit_page_length: 1,
	});
	if (!carts.length) return [];
	const lines = await api.post<{ item_code: string }[]>(
		'frappe.client.get_list',
		{
			doctype: 'Commera Cart Line',
			parent: 'Commera Cart',
			filters: { parent: carts[0].name },
			fields: ['item_code'],
			limit_page_length: 0,
		},
	);
	return lines.map((line) => line.item_code).sort();
}

async function expectServerCart(
	page: Page,
	owner: CartOwner,
	itemCodes: string[],
	match: 'equals' | 'contains' = 'equals',
) {
	await expect
		.poll(async () => {
			const codes = await getCartItemCodes(page, owner);
			return match === 'equals'
				? codes
				: itemCodes.filter((code) => codes.includes(code)).sort();
		})
		.toEqual([...itemCodes].sort());
}

async function continueAsGuest(page: Page) {
	if (!/\/cart\/checkout/.test(page.url())) {
		await page.goto(`${SHOP}/cart`);
		await page.getByRole('button', { name: 'Checkout' }).click();
		await page.getByRole('link', { name: 'Continue as Guest' }).click();
	}
	await page.waitForURL(/\/cart\/checkout/);
}

async function waitForEmail(api: Api, orderName: string) {
	let names: { name: string }[] = [];
	await expect
		.poll(
			async () => {
				names = await api.post<{ name: string }[]>('frappe.client.get_list', {
					doctype: 'Email Queue',
					filters: {
						reference_doctype: 'Sales Order',
						reference_name: orderName,
					},
				});
				return names.length;
			},
			{ timeout: 180_000, message: `no Email Queue row for ${orderName}` },
		)
		.toBe(1);
	return api.post<EmailQueue>('frappe.client.get', {
		doctype: 'Email Queue',
		name: names[0].name,
	});
}

async function getNames(api: Api, doctype: string, filters: unknown) {
	const rows = await api.post<{ name: string }[]>('frappe.client.get_list', {
		doctype,
		filters,
		limit_page_length: 0,
	});
	return rows.map((row) => row.name);
}

async function deleteAll(api: Api, doctype: string, filters: unknown) {
	for (const name of await getNames(api, doctype, filters))
		await api.post('frappe.client.delete', { doctype, name });
}

async function retireDocuments(api: Api, doctype: string, names: string[]) {
	for (const name of names) {
		const { docstatus } = await api.post<{ docstatus: number }>(
			'frappe.client.get_value',
			{
				doctype,
				filters: { name },
				fieldname: 'docstatus',
			},
		);
		if (docstatus === 1)
			await api.post('frappe.client.cancel', { doctype, name });
		else if (docstatus === 0)
			await api.post('frappe.client.delete', { doctype, name });
	}
}

async function removeOrder(api: Api, orderName: string) {
	await deleteAll(api, 'Commera Event', {
		reference_doctype: 'Sales Order',
		reference_name: orderName,
	});
	await deleteAll(api, 'Email Queue', {
		reference_doctype: 'Sales Order',
		reference_name: orderName,
	});
	await deleteAll(api, 'Storefront Analytics Event', { order_id: orderName });

	const invoices = await getNames(api, 'Sales Invoice', [
		['Sales Invoice Item', 'sales_order', '=', orderName],
	]);
	const payments = await getNames(api, 'Payment Entry', [
		[
			'Payment Entry Reference',
			'reference_name',
			'in',
			[orderName, ...invoices],
		],
	]);
	await retireDocuments(api, 'Payment Entry', payments);
	await retireDocuments(api, 'Sales Invoice', invoices);
	await retireDocuments(api, 'Sales Order', [orderName]);
}
