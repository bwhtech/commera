import { type Locator, type Page, expect } from '@playwright/test';
import { getSignupCode } from './bench';

export const SHOP = '/en';

export type Address = {
	first_name: string;
	last_name: string;
	email: string;
	phone_number: string;
	full_address: string;
	landmark: string;
	state: string;
	city: string;
	po_box: string;
};

export function makeAddress(email: string): Address {
	return {
		first_name: 'E2E',
		last_name: 'Shopper',
		email,
		phone_number: '+91 98200 12345',
		full_address: '12 Marine Drive',
		landmark: 'Near the station',
		state: 'Maharashtra',
		city: 'Mumbai',
		po_box: '400001',
	};
}

export async function expectToast(page: Page, text: string | RegExp) {
	await expect(page.getByText(text).first()).toBeVisible();
}

export async function addToCart(page: Page, productRoute: string) {
	await page.goto(`${SHOP}/products/${productRoute}`);
	const size = page
		.locator('input[name="product_size"]:not([disabled]):not(:checked)')
		.first();
	const sizeId = await size.getAttribute('id');
	await Promise.all([
		page.waitForURL(/[?&]size=/),
		page.locator(`label[for="${sizeId}"]`).click(),
	]);
	await page.getByRole('button', { name: 'Add To Cart' }).click();
	await expectToast(page, 'Item added to your bag');
}

export async function sendCode(page: Page, button: Locator) {
	const sent = page.waitForResponse(
		(response) => /commera\.api\.signup\.send_\w+_otp/.test(response.url()),
		{ timeout: 15_000 },
	);
	await button.click();
	const response = await sent.catch(() => null);
	if (!response) return 'no send request';
	const body = (await response.text().catch(() => '')).slice(0, 300);
	return `${response.url()} ${response
		.request()
		.postData()} -> ${response.status()} ${body}`;
}

export async function enterCode(page: Page, email: string, sent: string) {
	let code: number | null = null;
	await expect
		.poll(
			() => {
				code = getSignupCode(email);
				return code;
			},
			{
				timeout: 30_000,
				message: `no code in Redis for ${email}; send: ${sent}`,
			},
		)
		.toBeTruthy();
	const digits = String(code);
	const inputs = page.locator('.summer-auth-otp input');
	await expect(inputs).toHaveCount(6);
	for (let index = 0; index < 6; index++)
		await inputs.nth(index).fill(digits[index]);
	await page
		.locator('.summer-auth form button[type="submit"]', { hasText: 'Verify' })
		.click();
}

export async function signUp(page: Page, email: string) {
	await page.goto(`${SHOP}/cart`);
	await page.getByRole('link', { name: 'Login / Register' }).first().click();
	await page.getByRole('tab', { name: 'Sign Up' }).click();
	const form = page
		.locator('.summer-auth form')
		.filter({ hasText: 'First Name' });
	await form.locator('input[type="email"]').fill(email);
	await form.locator('input[type="text"]').nth(0).fill('E2E');
	await form.locator('input[type="text"]').nth(1).fill('Shopper');
	const sent = await sendCode(
		page,
		form.getByRole('button', { name: 'Sign Up' }),
	);
	await expect(page.locator('.summer-auth-otp input').first()).toBeVisible();
	await enterCode(page, email, sent);
	await expect(page.locator('.summer-auth-panel')).toBeHidden();
}

export async function signIn(page: Page, email: string) {
	await page.getByRole('link', { name: 'Login / Register' }).first().click();
	const form = page
		.locator('.summer-auth form')
		.filter({ has: page.getByRole('button', { name: 'Sign In' }) });
	await form.locator('input[type="email"]').fill(email);
	const sent = await sendCode(
		page,
		form.getByRole('button', { name: 'Sign In' }),
	);
	await expect(page.locator('.summer-auth-otp input').first()).toBeVisible();
	await enterCode(page, email, sent);
	await expect(page.locator('.summer-auth-panel')).toBeHidden();
}

export async function openCheckout(page: Page) {
	await page.goto(`${SHOP}/cart`);
	const placeOrder = page.getByRole('button', { name: 'Place Order' });
	await expect(placeOrder).toBeEnabled();
	await placeOrder.click();
	await page.waitForURL(/\/cart\/checkout/);
}

export async function saveAddress(page: Page, address: Address) {
	await page.waitForFunction(() => {
		const form = document.querySelector('[x-data^="summer_checkout"]');
		return (
			form &&
			(
				window as unknown as {
					Alpine?: { $data: (el: Element) => { billing?: unknown } };
				}
			).Alpine?.$data(form)?.billing
		);
	});
	await page.locator('#delivery_option_home').check();
	const newAddress = page.locator('#billing_new_address');
	if (await newAddress.isVisible()) await newAddress.check();
	for (const [field, value] of Object.entries(address))
		await page.locator(`#billing_${field}`).fill(value);
	await pickCountry(page, 'India');
	await page.getByRole('button', { name: 'Continue' }).click();
	await expectToast(page, /Delivery details saved/);
}

async function pickCountry(page: Page, country: string) {
	const input = page.locator('#billing_country');
	if ((await input.inputValue()) === country) return;
	await input.fill(country);
	await page
		.locator('#billing_country_listbox [role="option"]')
		.getByText(country, { exact: true })
		.click();
	await expect(input).toHaveValue(country);
}

export async function chooseDelivery(page: Page) {
	await expect(
		page.getByText('Checking delivery options for your address...'),
	).toBeHidden();
	if (await page.locator('input[name="shipping_option"]').count())
		await expect(
			page.locator('input[name="shipping_option"]:checked'),
		).toHaveCount(1);
}

export async function choosePayment(page: Page, label: string) {
	await page.locator('label[for^="payment_mode_"]', { hasText: label }).click();
	await page.locator('#accept_terms').check();
}

export async function getShownTotal(page: Page) {
	return page.evaluate(() => {
		const element = document.querySelector('[x-data^="summer_checkout"]');
		const data = (
			window as unknown as {
				Alpine: {
					$data: (el: Element) => { active_summary: { total: number } };
				};
			}
		).Alpine.$data(element as Element);
		return Number(data.active_summary.total);
	});
}

export async function placeOrder(page: Page) {
	const button = page.getByRole('button', { name: 'Place Order' });
	await expect(button).toBeEnabled();
	await button.click();
}

export async function readConfirmation(page: Page) {
	await page.waitForURL(/\/account\/orders\/confirmation/);
	await expect(
		page.getByRole('heading', { name: 'Order Confirmed' }).first(),
	).toBeVisible();
	const orderId = page.locator('p', { hasText: 'Order ID:' }).locator('strong');
	await expect(orderId).not.toBeEmpty();
	return (await orderId.innerText()).trim();
}

export async function viewOrder(page: Page, orderName: string) {
	await page.getByRole('link', { name: 'View Order' }).click();
	await page.waitForURL(/\/account\/orders/);
	await expect(page.getByText(orderName).first()).toBeVisible();
}
