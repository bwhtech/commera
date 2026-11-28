import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Browser, Locator, Page } from '@playwright/test';
import { Api } from '../lib/api';
import { login, newContext } from '../lib/auth';
import { PREFIX, e2eName, useCleanup } from '../lib/data';
import { ADMIN, FRESH_BASE } from '../lib/env';
import { expect, realProblems, test, watchPage } from '../lib/fixtures';

const SETTINGS = 'Commera Settings';
const STEP_KEY = 'commera:onboarding-step';
const SETUP_TIMEOUT = 180_000;
const PRODUCT_PHOTO =
	'/assets/commera/themes/summer_theme/images/shop/product/clothes/1.png';
const CSV_FIXTURE = path.join(
	import.meta.dirname,
	'..',
	'fixtures',
	'import-two-rows.csv',
);
const LOGO_PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
	'base64',
);

type Settings = Record<string, string | number | null>;
type Onboarding = {
	brand_logo: string;
	existing_store: { price_lists: { name: string; currency: string }[] } | null;
};
type Product = {
	title: string;
	collection: string;
	variants: { option: string; sizes: { size: string }[] }[];
};

const addCleanup = useCleanup();

function readSettings(api: Api) {
	return api.get<Settings>('frappe.client.get', {
		doctype: SETTINGS,
		name: SETTINGS,
	});
}

function writeSettings(api: Api, values: Settings) {
	return api.post('frappe.client.set_value', {
		doctype: SETTINGS,
		name: SETTINGS,
		fieldname: values,
	});
}

function admin(api: Api, method: string, args: Record<string, unknown> = {}) {
	return api.get<Record<string, unknown>>(`commera.api.admin.${method}`, args);
}

async function openPage(
	browser: Browser,
	role: 'admin' | 'merchant' | 'guest',
	problems: string[],
) {
	const context = await newContext(browser, role);
	const page = await context.newPage();
	watchPage(page, problems);
	return {
		context,
		page,
		api: Api.for(context, role === 'guest' ? '/' : '/commera'),
	};
}

function onboardingStep(page: Page, key: string) {
	return page.locator(`[data-onboarding-step="${key}"]`);
}

async function pressContinue(page: Page, from: string, to: string) {
	await onboardingStep(page, from)
		.getByRole('button', { name: 'Continue' })
		.click();
	await expect(onboardingStep(page, to)).toBeVisible();
}

async function reopenOnboarding(page: Page, api: Api) {
	const settings = await readSettings(api);
	if (settings.onboarding_completed)
		await writeSettings(api, { onboarding_completed: 0 });
	await page.goto('/commera');
	await page.evaluate((key) => localStorage.removeItem(key), STEP_KEY);
	await page.reload();
	await expect(onboardingStep(page, 'you')).toBeVisible();
	return settings;
}

async function restoreOnboarding(
	api: Api,
	settings: Settings,
	record: Onboarding,
) {
	await api.post('commera.api.admin.onboarding.save_brand', {
		brand_logo: record.brand_logo || '',
	});
	if (!(await readSettings(api)).company) return;
	await writeSettings(api, {
		store_name: settings.store_name || '',
		onboarding_completed: settings.onboarding_completed ? 1 : 0,
		...(settings.default_price_list
			? { default_price_list: settings.default_price_list }
			: {}),
	});
}

function withoutAbortedRequests(problems: string[]) {
	return realProblems(problems).filter(
		(entry) =>
			!(entry.startsWith('REQFAIL') && entry.endsWith('net::ERR_ABORTED')),
	);
}

async function finishOnboarding(page: Page, storeName: string) {
	const done = onboardingStep(page, 'done');
	await expect(done).toContainText(`${storeName} is ready`);
	await done
		.getByRole('button', { name: 'Go to Home' })
		.click({ timeout: SETUP_TIMEOUT });
	await expect(page.locator('[data-onboarding]')).toHaveCount(0, {
		timeout: 30_000,
	});
	await expect(page.locator('body')).toContainText('Orders');
	await page.reload();
	await expect(page.locator('body')).toContainText('Orders');
	await expect(page.locator('[data-onboarding]')).toHaveCount(0);
}

function importDialog(page: Page) {
	return page.getByRole('dialog').filter({ hasText: 'Import products' });
}

async function footerButton(dialog: Locator, name: string | RegExp) {
	const button = dialog.getByRole('button', { name });
	await expect(button).toBeEnabled();
	await button.click();
}

async function getSeededCollection(api: Api) {
	const [template] = await api.get<{ item_group: string }[]>(
		'frappe.client.get_list',
		{
			doctype: 'Item',
			filters: { has_variants: 1, disabled: 0 },
			fields: ['item_group'],
			limit_page_length: 1,
		},
	);
	return template.item_group;
}

async function deleteCollection(api: Api, collection: string) {
	const fallback = await getSeededCollection(api);
	const products = await api.get<{ parent: string }[]>(
		'frappe.client.get_list',
		{
			doctype: 'Product Collection',
			parent: 'Item',
			filters: { item_group: collection },
			fields: ['parent'],
			limit_page_length: 0,
		},
	);
	for (const { parent } of products) {
		await api.post('commera.api.admin.catalog.update_product', {
			item_template: parent,
			collection: fallback,
			collections: [fallback],
		});
	}
	for (const doctype of ['Item', 'Style Attribute Variant']) {
		const rows = await api.get<{ name: string }[]>('frappe.client.get_list', {
			doctype,
			filters: { item_group: collection },
			limit_page_length: 0,
		});
		for (const row of rows) {
			await api.post('frappe.client.set_value', {
				doctype,
				name: row.name,
				fieldname: 'item_group',
				value: fallback,
			});
		}
	}
	await api.post('frappe.client.delete', {
		doctype: 'Item Group',
		name: collection,
	});
}

async function addErpnextItems(adminApi: Api, itemCodes: string[]) {
	const settings = await readSettings(adminApi);
	const collection = await getSeededCollection(adminApi);
	for (const itemCode of itemCodes) {
		await adminApi.post('frappe.client.insert', {
			doc: {
				doctype: 'Item',
				item_code: itemCode,
				item_name: itemCode,
				item_group: collection,
				stock_uom: 'Nos',
				is_stock_item: 1,
				is_sales_item: 1,
				valuation_rate: 100,
				image: PRODUCT_PHOTO,
			},
		});
		addCleanup(() =>
			adminApi.post('frappe.client.set_value', {
				doctype: 'Item',
				name: itemCode,
				fieldname: 'disabled',
				value: 1,
			}),
		);
		await adminApi.post('frappe.client.insert', {
			doc: {
				doctype: 'Item Price',
				item_code: itemCode,
				price_list: settings.default_price_list,
				price_list_rate: 777,
			},
		});
	}
	const stockEntry = await adminApi.post<Record<string, unknown>>(
		'frappe.client.insert',
		{
			doc: {
				doctype: 'Stock Entry',
				stock_entry_type: 'Material Receipt',
				company: settings.company,
				items: itemCodes.map((itemCode) => ({
					item_code: itemCode,
					qty: 5,
					t_warehouse: settings.ecommerce_warehouse,
					basic_rate: 100,
				})),
			},
		},
	);
	await adminApi.post('frappe.client.submit', { doc: stockEntry });
}

async function archiveProducts(api: Api, itemTemplates: string[]) {
	for (const itemTemplate of itemTemplates) {
		await api.post('commera.api.admin.catalog.update_product', {
			item_template: itemTemplate,
			disabled: 1,
		});
	}
}

async function findProducts(api: Api, title: string) {
	return api.get<{ name: string; item_style: string; is_published: number }[]>(
		'frappe.client.get_list',
		{
			doctype: 'Style Attribute Variant',
			filters: { display_name: title },
			fields: ['name', 'item_style', 'is_published', 'route'],
		},
	);
}

test.describe(() => {
	test.describe.configure({ retries: 0 });

	test('a new owner onboards a fresh site with real clicks and lands on Home for good', async ({
		browser,
	}) => {
		test.skip(
			!FRESH_BASE,
			'COMMERA_FRESH_BASE names no site where setup never ran',
		);
		test.setTimeout(SETUP_TIMEOUT + 180_000);
		const storeName = e2eName('Fresh Store');
		const problems: string[] = [];
		const context = await browser.newContext({ baseURL: FRESH_BASE });
		await login(context.request, ADMIN.email, ADMIN.password, FRESH_BASE);
		const page = await context.newPage();
		watchPage(page, problems);
		const api = Api.for(context, '/commera', FRESH_BASE);

		const record = (await admin(
			api,
			'onboarding.get_onboarding',
		)) as Onboarding;
		const { active_theme: theme } = await admin(api, 'theme.get_editor_data');
		const settings = await reopenOnboarding(page, api);
		addCleanup(async () => {
			await restoreOnboarding(api, settings, record);
			await context.close();
		});

		const you = onboardingStep(page, 'you');
		const fullName = you.locator('input').first();
		if (!(await fullName.inputValue()).trim()) await fullName.fill('E2E Owner');
		await pressContinue(page, 'you', 'store');

		const store = onboardingStep(page, 'store');
		await store.locator('[data-onboarding-logo-input]').setInputFiles({
			name: 'e2e-logo.png',
			mimeType: 'image/png',
			buffer: LOGO_PNG,
		});
		await expect(store.getByAltText('Your logo')).toBeVisible();
		await store.getByLabel('Store name').fill(storeName);
		const accounting = store.locator('[data-onboarding-accounting]');
		await accounting.click();
		await expect(accounting).toHaveAttribute('aria-expanded', 'true');
		await expect(store).toContainText('Chart of accounts');
		const country = store.getByRole('button', { name: 'Country', exact: true });
		if ((await country.textContent())?.includes('Search countries')) {
			await country.click();
			await page.keyboard.type('India');
			await page.getByRole('option', { name: 'India', exact: true }).click();
		}

		await page.getByRole('button', { name: 'Back' }).click();
		await pressContinue(page, 'you', 'store');
		await expect(
			onboardingStep(page, 'store').getByLabel('Store name'),
		).toHaveValue(storeName);
		await pressContinue(page, 'store', 'done');
		const setup = page.locator(
			'[data-onboarding-setup="done"], [data-onboarding-setup="failed"]',
		);
		await expect(setup).toBeVisible({ timeout: SETUP_TIMEOUT });
		if ((await setup.getAttribute('data-onboarding-setup')) === 'failed') {
			const { error } = await admin(api, 'onboarding.get_setup_status');
			throw new Error(`the store setup job failed: ${error}`);
		}
		await finishOnboarding(page, storeName);

		const saved = await readSettings(api);
		expect(saved).toMatchObject({
			store_name: storeName,
			onboarding_completed: 1,
		});
		expect(saved.company).toBeTruthy();
		const after = (await admin(api, 'onboarding.get_onboarding')) as Onboarding;
		expect(after.brand_logo).toBeTruthy();
		expect((await admin(api, 'theme.get_editor_data')).active_theme).toBe(
			theme,
		);
		expect(withoutAbortedRequests(problems)).toEqual([]);
	});
});

test('an ERPNext site onboards onto its own company, price list and warehouse', async ({
	browser,
}) => {
	const problems: string[] = [];
	const { page, api } = await openPage(browser, 'admin', problems);
	const storeName = e2eName('ERPNext Store');
	const priceListName = e2eName('Selling');

	const record = (await admin(api, 'onboarding.get_onboarding')) as Onboarding;
	expect(
		record.existing_store,
		'a seeded site is onboarded as an existing ERPNext store',
	).toBeTruthy();
	const before = await readSettings(api);
	const priceList = await api.post<{ name: string }>('frappe.client.insert', {
		doc: {
			doctype: 'Price List',
			price_list_name: priceListName,
			currency: 'INR',
			selling: 1,
			enabled: 1,
		},
	});
	addCleanup(() =>
		api.post('frappe.client.set_value', {
			doctype: 'Price List',
			name: priceList.name,
			fieldname: 'enabled',
			value: 0,
		}),
	);
	const settings = await reopenOnboarding(page, api);
	addCleanup(() => restoreOnboarding(api, settings, record));

	await pressContinue(page, 'you', 'store');
	const store = onboardingStep(page, 'store');
	await store.getByLabel('Store name').fill(storeName);
	await expect(store.locator('[data-onboarding-accounting]')).toHaveCount(0);
	await store.getByRole('button', { name: 'Price list' }).click();
	await page.getByRole('option', { name: priceListName }).click();
	await pressContinue(page, 'store', 'done');
	await expect(page.locator('[data-onboarding-setup="done"]')).toBeVisible();
	await finishOnboarding(page, storeName);

	const saved = await readSettings(api);
	expect(saved).toMatchObject({
		store_name: storeName,
		company: before.company,
		default_price_list: priceListName,
		onboarding_completed: 1,
	});
	const warehouse = await api.get<{ company: string }>(
		'frappe.client.get_value',
		{
			doctype: 'Warehouse',
			filters: saved.ecommerce_warehouse,
			fieldname: 'company',
		},
	);
	expect(warehouse.company).toBe(before.company);
	expect(withoutAbortedRequests(problems)).toEqual([]);
});

test('ERPNext items import as drafts, publish with one click and sell on the storefront', async ({
	browser,
}) => {
	test.setTimeout(180_000);
	const problems: string[] = [];
	const { page, api } = await openPage(browser, 'admin', problems);
	const adminApi = api;
	const itemCodes = [e2eName('ERP-A'), e2eName('ERP-B')];
	await addErpnextItems(adminApi, itemCodes);

	await page.goto('/commera/products');
	await page.getByRole('button', { name: 'Import' }).first().click();
	const dialog = importDialog(page);
	await dialog.getByRole('button', { name: /ERPNext/ }).click();
	await footerButton(dialog, 'Continue');
	const selectionToggle = dialog.getByRole('button', {
		name: /^(Select all|Clear selection)$/,
	});
	await expect(selectionToggle).toBeEnabled();
	for (let attempt = 0; attempt < 2; attempt++) {
		if (/\b0 of \d+ selected/.test((await dialog.textContent()) ?? '')) break;
		const label = await selectionToggle.textContent();
		await selectionToggle.click();
		await expect(selectionToggle).not.toHaveText(label ?? '');
	}
	await expect(dialog).toContainText(/\b0 of \d+ selected/);
	await dialog.getByPlaceholder('Search items').fill(PREFIX);
	for (const itemCode of itemCodes) {
		await expect(
			dialog.getByText(itemCode, { exact: true }).first(),
		).toBeVisible();
	}
	for (const itemCode of itemCodes) {
		await expect(async () => {
			await dialog
				.getByRole('row')
				.filter({ hasText: itemCode })
				.getByRole('checkbox')
				.check({ timeout: 2_000 });
		}).toPass();
	}
	await footerButton(dialog, 'Import 2 items');
	await expect(dialog).toContainText('2 products are ready as drafts', {
		timeout: 60_000,
	});

	const drafts = (
		await Promise.all(
			itemCodes.map((itemCode) => findProducts(adminApi, itemCode)),
		)
	).flat();
	addCleanup(() => archiveProducts(api, itemCodes));
	expect(drafts.map((row) => row.item_style).sort()).toEqual(
		[...itemCodes].sort(),
	);
	expect(drafts.every((row) => row.is_published === 0)).toBe(true);

	await dialog.getByRole('button', { name: 'Publish all' }).click();
	await expect(dialog).toContainText('2 products are live');
	const published = (
		await Promise.all(
			itemCodes.map((itemCode) => findProducts(adminApi, itemCode)),
		)
	).flat();
	expect(published.every((row) => row.is_published === 1)).toBe(true);

	const shopper = await openPage(browser, 'guest', problems);
	const [product] = await findProducts(adminApi, itemCodes[0]);
	await shopper.page.goto(
		`/products/${(product as unknown as { route: string }).route}`,
	);
	await expect(shopper.page.locator('body')).toContainText(itemCodes[0]);
	await shopper.page
		.getByRole('button', { name: /Add To Cart/i })
		.first()
		.click();
	await expect(shopper.page.locator('body')).toContainText(
		'Item added to your bag',
	);
	await expect
		.poll(async () => {
			const cart = await shopper.api.get<{
				lines: { variant: { item_code: string } }[];
			} | null>('commera.api.server_cart.get_server_cart');
			return cart?.lines.map((line) => line.variant.item_code) ?? [];
		})
		.toContain(itemCodes[0]);
	expect(withoutAbortedRequests(problems)).toEqual([]);
});

test('a spreadsheet import creates the product with its sizes', async ({
	browser,
}) => {
	test.setTimeout(180_000);
	const problems: string[] = [];
	const { page, api } = await openPage(browser, 'admin', problems);
	const title = e2eName('Hold Tee');
	const csv = readFileSync(CSV_FIXTURE, 'utf8')
		.replaceAll('E2E Hold Tee', title)
		.replaceAll('Tops', await getSeededCollection(api));

	await page.goto('/commera/products');
	await page.getByRole('button', { name: 'Import' }).first().click();
	const dialog = importDialog(page);
	await dialog.getByRole('button', { name: /Spreadsheet/ }).click();
	await footerButton(dialog, 'Continue');
	await dialog.locator('input[type="file"]').setInputFiles({
		name: 'import-two-rows.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(csv),
	});
	await footerButton(dialog, 'Continue');
	await footerButton(dialog, 'Continue');
	await footerButton(dialog, 'Skip photos for now');
	await footerButton(dialog, 'Import 2 products');
	await expect(dialog.getByText('Done', { exact: true })).toBeVisible({
		timeout: 60_000,
	});
	await expect(dialog).toContainText('products created');

	const rows = await findProducts(api, title);
	addCleanup(() =>
		archiveProducts(api, [...new Set(rows.map((row) => row.item_style))]),
	);
	expect(rows).toHaveLength(1);
	const product = await api.get<Product>(
		'commera.api.admin.catalog.get_product',
		{
			item_template: rows[0].item_style,
		},
	);
	expect(product.title).toBe(title);
	expect(
		product.variants
			.flatMap((variant) => variant.sizes.map((row) => row.size))
			.sort(),
	).toEqual(['L', 'M']);
	expect(realProblems(problems)).toEqual([]);
});

test('the owner adds a collection, an attribute and a product from the option and size grid', async ({
	browser,
}) => {
	test.setTimeout(180_000);
	const problems: string[] = [];
	const { page, api } = await openPage(browser, 'admin', problems);
	const collection = e2eName('Collection');
	const attribute = `${PREFIX}Fabric`;
	const title = e2eName('Tee');

	await page.goto('/commera/collections');
	await page.getByRole('button', { name: 'Create collection' }).click();
	await page.getByRole('dialog').locator('input').first().fill(collection);
	await page
		.getByRole('dialog')
		.getByRole('button', { name: /^(Create|Save|Submit)$/ })
		.click();
	await expect(page.locator('body')).toContainText(collection);
	expect(
		await api.get<string[]>('commera.api.admin.catalog.get_collections'),
	).toContain(collection);
	addCleanup(() => deleteCollection(api, collection));

	await page.goto('/commera/attributes');
	await page.getByRole('button', { name: 'New attribute' }).click();
	const attributeInputs = page.getByRole('dialog').locator('input');
	await attributeInputs.nth(0).fill(attribute);
	await attributeInputs.nth(1).fill('Linen, Denim');
	await page
		.getByRole('dialog')
		.getByRole('button', { name: /^(Create|Save|Submit)$/ })
		.click();
	await expect
		.poll(async () => {
			const attributes = await api.get<
				{ name: string; values: { value: string }[] }[]
			>('commera.api.admin.catalog.get_attributes');
			return attributes
				.find((row) => row.name === attribute)
				?.values.map((row) => row.value);
		})
		.toEqual(['Linen', 'Denim']);
	addCleanup(() =>
		api.post('frappe.client.delete', {
			doctype: 'Item Attribute',
			name: attribute,
		}),
	);

	await page.goto('/commera/products');
	await page.getByRole('button', { name: 'Add product' }).first().click();
	const dialog = page
		.getByRole('dialog')
		.filter({ hasText: 'Photos come next' });
	await dialog.getByPlaceholder('Cotton oversized tee').fill(title);
	await dialog.getByRole('combobox').first().click();
	await page.getByRole('option', { name: collection }).click();

	await dialog.getByRole('button', { name: 'Color', exact: true }).click();
	for (const colour of ['Red', 'Blue'])
		await page.getByRole('option', { name: colour, exact: true }).click();
	await page.keyboard.press('Escape');
	await dialog.getByRole('button', { name: 'Sizes', exact: true }).click();
	for (const size of ['S', 'M', 'L'])
		await page.getByRole('option', { name: size, exact: true }).click();
	await page.keyboard.press('Escape');
	await expect(dialog).toContainText('6 variants will be created');

	for (const cell of ['Blue in size S', 'Blue in size L'])
		await dialog.getByLabel(cell).click();
	await expect(dialog).toContainText('4 variants will be created');
	await dialog.getByLabel('Price', { exact: true }).fill('999');
	await dialog.getByLabel(/Discounted price/).fill('799');
	await dialog.getByRole('button', { name: 'Add product' }).click();

	await expect(page).toHaveURL(/\/commera\/products\/[^/?#]+$/);
	const itemTemplate = decodeURIComponent(page.url().split('/').pop() || '');
	addCleanup(() => archiveProducts(api, [itemTemplate]));
	await page.waitForLoadState('networkidle');
	await page.reload();
	await expect(page.locator('body')).toContainText(title);

	const product = await api.get<Product>(
		'commera.api.admin.catalog.get_product',
		{
			item_template: itemTemplate,
		},
	);
	expect(product.title).toBe(title);
	expect(product.collection).toBe(collection);
	expect(
		Object.fromEntries(
			product.variants.map((row) => [row.option, row.sizes.length]),
		),
	).toEqual({
		Red: 3,
		Blue: 1,
	});
	expect(withoutAbortedRequests(problems)).toEqual([]);
});

test.fail(
	'a merchant runs the ERPNext import (https://github.com/bwhtech/commera/issues/609)',
	async ({ browser }) => {
		test.setTimeout(120_000);
		const problems: string[] = [];
		const adminApi = (await openPage(browser, 'admin', problems)).api;
		const { api } = await openPage(browser, 'merchant', problems);
		const itemCode = e2eName('ERP-Merchant');
		await addErpnextItems(adminApi, [itemCode]);
		addCleanup(() => archiveProducts(adminApi, [itemCode]));

		const { job_id: jobId } = await api.post<{ job_id: string }>(
			'commera.api.admin.erpnext_import.start_erpnext_import',
			{ item_codes: [itemCode] },
		);
		await expect
			.poll(
				async () =>
					(
						await api.get<{ status: string }>(
							'commera.api.admin.erpnext_import.get_erpnext_import_status',
							{ job_id: jobId },
						)
					).status,
				{ timeout: 60_000 },
			)
			.toMatch(/^(done|failed)$/);
		const status = await api.get<{ created: number; failed: unknown[] }>(
			'commera.api.admin.erpnext_import.get_erpnext_import_status',
			{ job_id: jobId },
		);
		expect(status.failed).toEqual([]);
		expect(status.created).toBe(1);
	},
);

test.fail(
	'a merchant adds a product (https://github.com/bwhtech/commera/issues/609)',
	async ({ browser }) => {
		const problems: string[] = [];
		const adminApi = (await openPage(browser, 'admin', problems)).api;
		const { api } = await openPage(browser, 'merchant', problems);
		const product = await api.post<{ name: string }>(
			'commera.api.admin.catalog.create_product',
			{
				title: e2eName('Merchant Tee'),
				collection: await getSeededCollection(adminApi),
				option_sizes: [{ option: 'Red', sizes: ['M'] }],
				price: 999,
				sale_price: 799,
			},
		);
		addCleanup(() => archiveProducts(adminApi, [product.name]));
		expect(product.name).toBeTruthy();
	},
);
