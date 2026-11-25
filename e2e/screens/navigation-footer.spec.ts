import type { Page } from '@playwright/test';
import { Api } from '../lib/api';
import { PREFIX, e2eName, useCleanup } from '../lib/data';
import { ADMIN_STATE } from '../lib/env';
import { expect, realProblems, test } from '../lib/fixtures';

const ADMIN_API = 'commera.api.admin.';

type MenuNode = { name: string; label: string; children: MenuNode[] };
type FooterColumn = { name: string; title: string };

function exactText(label: string) {
	return new RegExp(
		`^\\s*${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`,
	);
}

function byText(page: Page, selector: string, label: string) {
	return page
		.locator(`${selector}:visible`)
		.filter({ hasText: exactText(label) })
		.first();
}

async function openNavigation(page: Page) {
	await page.goto('/commera/storefront/navigation');
	await expect(
		page.locator('button[aria-label="Entry actions"]').first(),
	).toBeVisible();
}

async function openFooterTab(page: Page) {
	await openNavigation(page);
	await byText(page, 'button', 'Footer').click();
	await expect(
		page.locator('button[aria-label="Column actions"]').first(),
	).toBeVisible();
}

async function openRowMenu(page: Page, label: string, ariaLabel: string) {
	const handle = await page.evaluateHandle(
		({ needle, aria }) => {
			const buttons = [
				...document.querySelectorAll(`button[aria-label="${aria}"]`),
			];
			return buttons.find((button) => {
				const row = button.closest('div, li');
				const container = row?.parentElement?.closest('div') ?? row;
				return (
					((container as HTMLElement | null)?.innerText || '')
						.trim()
						.split('\n')[0] === needle
				);
			});
		},
		{ needle: label, aria: ariaLabel },
	);
	const element = handle.asElement();
	if (!element) throw new Error(`no "${ariaLabel}" menu for row "${label}"`);
	await element.click();
}

async function typeIntoDialog(page: Page, value: string) {
	await page.locator('[role="dialog"] input').first().fill(value);
}

function editorProblems(problems: string[]) {
	return realProblems(problems).filter(
		(entry) => !entry.endsWith('net::ERR_ABORTED'),
	);
}

async function confirmDialog(page: Page, label: string) {
	await byText(page, '[role="dialog"] button', label).click();
	await expect(page.locator('[role="dialog"]:visible')).toHaveCount(0);
}

test.describe('storefront', () => {
	test.use({ storageState: ADMIN_STATE });

	const cleanup = useCleanup();
	let api: Api;

	test.beforeAll(async ({ playwright }) => {
		const requestContext = await playwright.request.newContext({
			storageState: ADMIN_STATE,
		});
		api = new Api(requestContext);
		cleanup(() => requestContext.dispose());
	});

	const getMenu = async () =>
		(
			await api.get<{ menu: MenuNode[] }>(
				`${ADMIN_API}navigation.get_editor_data`,
			)
		).menu;
	const getColumns = async () =>
		(
			await api.get<{ columns: FooterColumn[] }>(
				`${ADMIN_API}footer.get_editor_data`,
			)
		).columns;
	const deleteNodeOnCleanup = (name: string) =>
		cleanup(() =>
			api.post(`${ADMIN_API}navigation.delete_node`, { name }).catch(() => {}),
		);

	test('adds and deletes a navigation section', async ({ page, problems }) => {
		const entry = e2eName('Nav');
		await openNavigation(page);

		await byText(page, 'button', 'Add section').click();
		await typeIntoDialog(page, entry);
		await confirmDialog(page, 'Add');

		await expect
			.poll(async () => (await getMenu()).some((row) => row.label === entry))
			.toBe(true);

		await openNavigation(page);
		await expect(
			page.locator('body'),
			'the new section did not survive a reload',
		).toContainText(entry);

		const node = (await getMenu()).find((row) => row.label === entry);
		expect(node, 'the new section is not in the persisted menu').toBeTruthy();
		deleteNodeOnCleanup(node?.name ?? '');

		await openRowMenu(page, entry, 'Entry actions');
		await byText(page, '[role="menuitem"]', 'Delete').click();
		await confirmDialog(page, 'Delete');

		await openNavigation(page);
		await expect(
			page.locator('body'),
			'the deleted section came back after a reload',
		).not.toContainText(entry);
		expect(
			(await getMenu()).some((row) => row.label === entry),
			'the section is still persisted',
		).toBe(false);

		expect(
			editorProblems(problems),
			'the navigation editor reported browser problems',
		).toEqual([]);
	});

	test('shows an entry added inside a section without expanding it', async ({
		page,
		problems,
	}) => {
		const entry = e2eName('Nav');
		const childEntry = e2eName('Nav Child');
		const parent = await api.post<{ menu: MenuNode[] }>(
			`${ADMIN_API}navigation.add_node`,
			{ parent: '', display_name: entry },
		);
		const section = parent.menu.find((row) => row.label === entry);
		expect(section, 'the API did not create the section').toBeTruthy();
		deleteNodeOnCleanup(section?.name ?? '');

		await openNavigation(page);
		await openRowMenu(page, entry, 'Entry actions');
		await byText(page, '[role="menuitem"]', 'Add entry inside').click();
		await typeIntoDialog(page, childEntry);
		await confirmDialog(page, 'Add');

		await expect
			.poll(
				async () =>
					(await getMenu())
						.find((row) => row.label === entry)
						?.children.some((row) => row.label === childEntry),
				{ message: 'the child entry is not persisted under its section' },
			)
			.toBe(true);
		const child = (await getMenu())
			.find((row) => row.label === entry)
			?.children.find((row) => row.label === childEntry);
		deleteNodeOnCleanup(child?.name ?? '');
		await expect(
			page.locator('body'),
			'the new child is hidden inside a collapsed section',
		).toContainText(childEntry);

		await openNavigation(page);
		await expect(
			page.locator('body'),
			'top-level sections no longer open on load',
		).toContainText(childEntry);
		expect(
			editorProblems(problems),
			'the navigation editor reported browser problems',
		).toEqual([]);
	});

	test('draws an icon on every editor menu item', async ({ page }) => {
		const missing: string[] = [];
		const menus = [
			{ open: () => openNavigation(page), aria: 'Entry actions' },
			{ open: () => openFooterTab(page), aria: 'Column actions' },
			{ open: () => openFooterTab(page), aria: 'Link actions' },
		];
		for (const menu of menus) {
			await menu.open();
			const trigger = page.locator(`button[aria-label="${menu.aria}"]`).first();
			await expect(trigger, `no "${menu.aria}" menu on screen`).toBeVisible();
			await trigger.click();
			const menuItems = page.locator('[role="menuitem"]');
			await expect(
				menuItems.first(),
				`the "${menu.aria}" menu opened empty`,
			).toBeVisible();
			const items = await menuItems.evaluateAll((nodes) =>
				nodes.map((node) => ({
					label: (node as HTMLElement).innerText.trim(),
					icon: Boolean(node.querySelector('svg, [class*="lucide-"]')),
				})),
			);
			missing.push(
				...items
					.filter((item) => !item.icon)
					.map((item) => `${menu.aria}: ${item.label}`),
			);
			await page.keyboard.press('Escape');
		}
		expect(missing, 'menu items without an icon').toEqual([]);
	});

	test('adds, renames and deletes a footer column', async ({
		page,
		problems,
	}) => {
		const column = e2eName('Column');
		const renamed = e2eName('Column Renamed');
		cleanup(async () => {
			for (const row of await getColumns()) {
				if (row.title.startsWith(PREFIX)) {
					await api
						.post(`${ADMIN_API}footer.delete_section`, { name: row.name })
						.catch(() => {});
				}
			}
		});
		await openFooterTab(page);

		await byText(page, 'button', 'Add column').click();
		await typeIntoDialog(page, column);
		await confirmDialog(page, 'Add');

		await expect
			.poll(async () =>
				(await getColumns()).some((row) => row.title === column),
			)
			.toBe(true);
		await openFooterTab(page);
		await expect(
			page.locator('body'),
			'the new column did not survive a reload',
		).toContainText(column);

		await openRowMenu(page, column, 'Column actions');
		await byText(page, '[role="menuitem"]', 'Rename').click();
		await typeIntoDialog(page, renamed);
		await confirmDialog(page, 'Rename');

		await openFooterTab(page);
		expect(
			(await getColumns()).some((row) => row.title === renamed),
			'the rename was not persisted',
		).toBe(true);

		await openRowMenu(page, renamed, 'Column actions');
		await byText(page, '[role="menuitem"]', 'Delete column').click();
		await confirmDialog(page, 'Delete column');

		await openFooterTab(page);
		expect(
			(await getColumns()).some((row) => row.title.startsWith(PREFIX)),
			'the deleted column is still persisted',
		).toBe(false);

		expect(
			editorProblems(problems),
			'the footer editor reported browser problems',
		).toEqual([]);
	});
});
