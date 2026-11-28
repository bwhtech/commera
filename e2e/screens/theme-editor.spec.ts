import type { Page, Route } from '@playwright/test';
import { Api } from '../lib/api';
import { ADMIN_STATE } from '../lib/env';
import { expect, test } from '../lib/fixtures';

const SLOW_RENDER_MS = 1500;
const WORKSPACE_STORAGE = [
	'commera:theme-editor:zoom',
	'commera-theme-editor-panels',
];

const REFUSAL = {
	status: 417,
	contentType: 'application/json',
	body: JSON.stringify({
		errors: [
			{
				type: 'ValidationError',
				message: 'A section setting has the wrong type.',
			},
		],
	}),
};

type Theme = { name: string; live: boolean; theme_type: string };
type EditorData = { themes: Theme[] };
type SectionSchema = {
	type: string;
	groups?: string[];
	settings?: { id: string; type: string; default?: string }[];
	blocks?: Record<string, { name: string }>;
};
type LayoutEditor = { pages: string[]; section_schemas: SectionSchema[] };

const delay = (milliseconds: number) =>
	new Promise((resolve) => setTimeout(resolve, milliseconds));

const exactText = (label: string) =>
	new RegExp(`^\\s*${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`);

const frameSelector = (device: string) =>
	`[data-preview-device="${device}"] iframe[data-preview-frame="visible"]`;

const editorUrl = (theme: Theme) =>
	`/commera/storefront/theme/${encodeURIComponent(theme.name)}/editor`;

const headerButton = (page: Page, label: string) =>
	page
		.locator('header button')
		.filter({ hasText: exactText(label) })
		.first();

const firstSection = (page: Page) =>
	page.locator('[data-tree-node^="section:"]').first();

const settingsPanel = (page: Page) => page.locator('[data-settings-panel]');

const saveSettingsButton = (page: Page) =>
	page.locator('[data-theme-settings-panel] > :last-child button').first();

async function gotoEditor(page: Page, theme: Theme) {
	await page.goto(editorUrl(theme));
	await expect(firstSection(page)).toBeVisible({ timeout: 30000 });
}

async function openEditor(
	page: Page,
	theme: Theme,
	{ clearWorkspace = false } = {},
) {
	await page.goto(editorUrl(theme));
	if (clearWorkspace) {
		await page.evaluate((keys) => {
			for (const key of Object.keys(localStorage)) {
				if (keys.some((part) => key.includes(part)))
					localStorage.removeItem(key);
			}
		}, WORKSPACE_STORAGE);
		await page.reload({ waitUntil: 'networkidle' });
	}
	await expect(firstSection(page)).toBeVisible({ timeout: 30000 });
	await expect(
		page.locator('[data-preview-frame="visible"]').first(),
	).toBeVisible({
		timeout: 30000,
	});
}

const panelWidth = (page: Page, name: string) =>
	page
		.locator(`[data-editor-panel="${name}"]`)
		.evaluate((element) => Math.round(element.getBoundingClientRect().width));

const previewScale = (page: Page) =>
	page
		.locator('[data-preview-canvas]')
		.evaluate((element) =>
			Number((element as HTMLElement).dataset.previewScale),
		);

async function box(page: Page, selector: string) {
	const result = await page.locator(selector).first().boundingBox();
	if (!result) throw new Error(`${selector} has no box`);
	return result;
}

function inFrame<Result, Arg = undefined>(
	page: Page,
	device: string,
	callback: (iframe: HTMLIFrameElement, arg: Arg) => Result,
	arg?: Arg,
) {
	return page
		.locator(frameSelector(device))
		.evaluate(callback as (element: Element, arg: Arg) => Result, arg as Arg);
}

const outlineShown = (page: Page, device: string) =>
	inFrame(
		page,
		device,
		(iframe) =>
			(iframe.contentDocument?.querySelectorAll('[data-commera-outline]')
				.length ?? 0) > 0,
	);

async function setZoom(page: Page, value: string, expected: number) {
	await page.click(`[aria-label="Preview zoom"] [data-value="${value}"]`);
	await expect.poll(() => previewScale(page)).toBe(expected);
}

async function wheelOver(page: Page, device: string) {
	const frame = await box(page, frameSelector(device));
	await page.mouse.move(frame.x + frame.width / 2, frame.y + frame.height / 2);
	await page.mouse.wheel(0, 600);
}

async function dragBy(
	page: Page,
	selector: string,
	deltaX: number,
	deltaY = 0,
) {
	const handle = await box(page, selector);
	const startX = handle.x + handle.width / 2;
	const startY = handle.y + Math.min(handle.height / 2, 300);
	await page.mouse.move(startX, startY);
	await page.mouse.down();
	await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 8 });
	await page.mouse.up();
}

async function openThemeSettings(page: Page) {
	await page.click('[data-theme-settings-toggle]');
	await page.waitForFunction(
		() => {
			const panel = document.querySelector(
				'[data-theme-layout-editor] > aside',
			);
			const column = document.querySelector('[data-editor-panel="settings"]');
			return (
				panel &&
				column &&
				Math.round(panel.getBoundingClientRect().width) ===
					Math.round(column.getBoundingClientRect().width)
			);
		},
		undefined,
		{ timeout: 5000 },
	);
}

async function pickPreviewOption(page: Page, label: string) {
	await page.click(
		'[data-zoom-controls] button[aria-label="More preview options"]',
	);
	await expect(page.locator('[data-preview-options]')).toBeVisible();
	const languages: Record<string, string> = {
		'Left to right': 'en',
		'Right to left': 'ar',
	};
	if (languages[label]) {
		await page.click(
			`[data-preview-options] [aria-label="Preview language"] [data-value="${languages[label]}"]`,
		);
	} else {
		await page.click(`[data-preview-options] [aria-label="${label}"]`);
	}
	await page.keyboard.press('Escape');
	await expect(page.locator('[data-preview-options]')).toBeHidden();
}

const clickButton = (page: Page, label: string) =>
	page.locator(`button[aria-label="${label}"]`).first().click();

async function firstTextThemeSetting(page: Page) {
	return page.evaluate(() => {
		const input = [
			...document.querySelectorAll<HTMLInputElement>('input[id^="theme-"]'),
		].find(
			(element) =>
				element.type === 'text' && !element.readOnly && !element.disabled,
		);
		return input ? { id: input.id, value: input.value } : null;
	});
}

async function headerStates(page: Page) {
	return page
		.locator('header button')
		.evaluateAll((buttons) =>
			Object.fromEntries(
				(buttons as HTMLButtonElement[])
					.filter((button) =>
						['Discard', 'Save', 'Publish'].includes(
							button.textContent?.trim() ?? '',
						),
					)
					.map((button) => [button.textContent?.trim(), !button.disabled]),
			),
		);
}

async function addSection(page: Page, type: string) {
	await page
		.locator(
			'xpath=.//button[normalize-space()="Add section" or @aria-label="Add section to Home page"]',
		)
		.first()
		.click();
	await page.click(`[data-section-type="${type}"]`);
}

test.describe('theme editor', () => {
	test.use({ storageState: ADMIN_STATE });
	test.describe.configure({ timeout: 120_000 });

	let theme: Theme;
	let api: Api;

	test.beforeEach(async ({ page }) => {
		page.on('dialog', (dialog) => dialog.accept());
		api = Api.for(page.context());
		const data = await api.get<EditorData>(
			'commera.api.admin.theme.get_editor_data',
		);
		const live = data.themes.find(
			(candidate) => candidate.live && candidate.theme_type === 'Sections',
		);
		test.skip(!live, 'the live theme is not a Sections theme');
		theme = live as Theme;
	});

	test('The top bar keeps Save and Publish on and shows Discard only with something to discard', async ({
		page,
	}) => {
		await openEditor(page, theme);
		const toastAfter = async (label: string, message: string) => {
			await headerButton(page, label).click();
			await expect(
				page
					.locator('[data-sonner-toast]')
					.filter({ hasText: message })
					.first(),
			).toBeVisible({ timeout: 5000 });
		};

		const headerText = await page.locator('header').first().innerText();
		const pending = headerText.includes('Unpublished changes');
		if (pending) {
			expect(await headerStates(page)).toEqual({
				Discard: true,
				Save: true,
				Publish: true,
			});
		} else {
			expect(headerText).toContain('Published');
			expect(
				await headerStates(page),
				'nothing to discard, so no Discard',
			).toEqual({ Save: true, Publish: true });
			await toastAfter('Publish', 'Already published');
		}
		await toastAfter('Save', 'Nothing to save');

		await firstSection(page).click();
		const hide = page
			.locator('[data-settings-panel] button[aria-label="Hide section"]')
			.first();
		await expect(hide).toBeVisible();
		await hide.click();
		await expect
			.poll(() => headerStates(page))
			.toEqual({ Discard: true, Save: true, Publish: true });

		await page
			.locator('[data-settings-panel] button[aria-label="Show section"]')
			.first()
			.click();
		await expect
			.poll(async () => 'Discard' in (await headerStates(page)), {
				message: 'undoing the edit leaves only what was there before',
			})
			.toBe(pending);
	});

	test('A refused save keeps the edit unsaved and publishes nothing', async ({
		page,
	}) => {
		const calls: string[] = [];
		await page.route(
			/theme_layout\.(save_draft|publish)$/,
			async (route: Route) => {
				const method = route
					.request()
					.url()
					.match(/theme_layout\.(save_draft|publish)$/)?.[1];
				if (method) calls.push(method);
				if (method === 'save_draft') {
					await delay(SLOW_RENDER_MS);
					await route.fulfill(REFUSAL);
				} else {
					await route.continue();
				}
			},
		);

		await gotoEditor(page, theme);
		await firstSection(page).click();
		const hide = page.locator('button[aria-label^="Hide "]').first();
		await expect(hide).toBeVisible();
		await hide.click();

		const header = page.locator('header').first();
		const saveButton = headerButton(page, 'Save');
		await expect(saveButton).toBeEnabled();
		await saveButton.click();
		await expect
			.poll(async () =>
				page
					.locator('header button')
					.evaluateAll((buttons) =>
						Object.fromEntries(
							(buttons as HTMLButtonElement[])
								.filter((button) =>
									['Discard', 'Save', 'Publish'].includes(
										button.textContent?.trim() ?? '',
									),
								)
								.map((button) => [
									button.textContent?.trim(),
									button.getAttribute('aria-busy')
										? 'loading'
										: button.disabled
										  ? 'disabled'
										  : 'enabled',
								]),
						),
					),
			)
			.toEqual({ Discard: 'disabled', Save: 'loading', Publish: 'disabled' });
		await expect(saveButton).not.toHaveAttribute('aria-busy', /.+/, {
			timeout: SLOW_RENDER_MS + 5000,
		});

		expect(calls).toEqual(['save_draft']);
		await expect(
			header,
			'the edit is kept and still unpublished',
		).toContainText('Unpublished changes');
		await expect(
			saveButton,
			'Save stays on so the edit can be retried',
		).toBeEnabled();
		await page.locator('button[aria-label^="Show "]').first().click();
	});

	test('A slow preview render dims the preview until the new page swaps in', async ({
		page,
	}) => {
		await page.route(
			(url) => url.href.includes('/theme_editor_preview'),
			async (route) => {
				if (route.request().method() === 'POST') await delay(SLOW_RENDER_MS);
				await route.continue();
			},
		);

		await gotoEditor(page, theme);
		const rendering = page.locator('[data-preview-rendering]');
		await expect(
			page.locator('iframe[data-preview-frame="visible"]'),
		).toBeAttached({ timeout: 30000 });
		await expect(rendering).toBeHidden({ timeout: 30000 });
		await firstSection(page).click();
		const hide = page.locator('button[aria-label^="Hide "]').first();
		await expect(hide).toBeVisible();
		await hide.click();

		await expect(rendering.first()).toBeVisible({
			timeout: SLOW_RENDER_MS + 3000,
		});
		await expect
			.poll(
				() =>
					page.evaluate(() => {
						const frame = document
							.querySelector('iframe[data-preview-frame="visible"]')
							?.getBoundingClientRect();
						if (!frame) return false;
						const top = document.elementFromPoint(
							frame.left + frame.width / 2,
							frame.top + frame.height / 2,
						);
						return Boolean(top?.closest('[data-preview-rendering]'));
					}),
				{
					message: 'the overlay sits over the preview and takes its clicks',
					timeout: SLOW_RENDER_MS,
				},
			)
			.toBe(true);

		await expect(rendering).toBeHidden({ timeout: 30000 });
		const settled = await page.evaluate(() =>
			[
				...((
					document.querySelector(
						'iframe[data-preview-frame="visible"]',
					) as HTMLIFrameElement
				).contentDocument?.querySelectorAll('.wow') ?? []),
			].every(
				(element) =>
					getComputedStyle(element).visibility === 'visible' &&
					getComputedStyle(element).animationName === 'none',
			),
		);
		expect(
			settled,
			'the re-rendered page lands without entrance animations',
		).toBe(true);

		await page.locator('button[aria-label^="Show "]').first().click();
		await expect(rendering.first()).toBeVisible({
			timeout: SLOW_RENDER_MS + 3000,
		});
		await expect(rendering).toBeHidden({ timeout: 30000 });
	});

	test('A failed preview render clears the overlay and keeps the last page usable', async ({
		page,
	}) => {
		await openEditor(page, theme);
		const rendering = page.locator('[data-preview-rendering]');
		await expect(rendering).toBeHidden({ timeout: 30000 });

		const failRender = async (route: Route) => {
			if (route.request().method() === 'POST') {
				await delay(SLOW_RENDER_MS);
				await route.fulfill({
					status: 502,
					contentType: 'text/html',
					body: '<h1>502 Bad Gateway</h1>',
				});
			} else {
				await route.continue();
			}
		};
		const matchesPreview = (url: URL) =>
			url.href.includes('/theme_editor_preview');
		await page.route(matchesPreview, failRender);

		try {
			await firstSection(page).click();
			const hide = page.locator('button[aria-label^="Hide "]').first();
			await expect(hide).toBeVisible();
			await hide.click();
			await expect(rendering.first()).toBeVisible({
				timeout: SLOW_RENDER_MS + 3000,
			});
			await expect(rendering).toBeHidden({ timeout: SLOW_RENDER_MS + 5000 });
			await expect(
				page.locator('body'),
				'the merchant is told the preview did not update',
			).toContainText('The preview could not be updated');
			const shown = await inFrame(
				page,
				'desktop',
				(iframe) => iframe.contentDocument?.body.innerText ?? '',
			);
			expect(shown, 'the last good page stays in the preview').not.toContain(
				'502 Bad Gateway',
			);
		} finally {
			await page.unroute(matchesPreview, failRender);
			await page.locator('button[aria-label^="Show "]').first().click();
		}
	});

	async function saveThemeSetting(
		page: Page,
		afterSave: (changed: string) => Promise<void>,
	) {
		await page.goto(editorUrl(theme));
		await page.waitForFunction(
			() =>
				(
					document.querySelector(
						'iframe[data-preview-frame="visible"]',
					) as HTMLIFrameElement | null
				)?.contentDocument?.querySelector('[data-commera-section]'),
			undefined,
			{ timeout: 30000 },
		);
		await openThemeSettings(page);

		const field = await page.evaluate(() => {
			const preview = (
				document.querySelector(
					'iframe[data-preview-frame="visible"]',
				) as HTMLIFrameElement
			).contentDocument?.documentElement.outerHTML;
			const inputs = [
				...document.querySelectorAll<HTMLInputElement>('input[id^="theme-"]'),
			].filter(
				(element) =>
					element.type === 'text' && !element.readOnly && !element.disabled,
			);
			const input =
				inputs.find((element) => element.id.endsWith('_url')) ??
				inputs.find(
					(element) => element.value && preview.includes(element.value),
				);
			return input
				? {
						id: input.id,
						fieldname: input.id.replace('theme-', ''),
						value: input.value,
				  }
				: null;
		});
		test.skip(!field, 'no theme setting of this theme shows in the preview');
		if (!field) return;

		const changed = field.fieldname.endsWith('_url')
			? `https://example.com/e2e-${Date.now()}`
			: `${field.value} E2E`;
		const posts: string[] = [];
		page.on('request', (request) => {
			if (
				request.method() === 'POST' &&
				request.url().includes('/theme_editor_preview')
			)
				posts.push(request.url());
		});

		try {
			await page.locator(`#${field.id}`).click({ clickCount: 3 });
			await page.keyboard.type(changed);
			await saveSettingsButton(page).click();
			await expect.poll(() => posts.length).toBeGreaterThan(0);
			await page.waitForTimeout(1000);
			expect(posts.length, 'one preview render for one saved setting').toBe(1);
			await afterSave(changed);
		} finally {
			await api.post('commera.api.admin.theme.save_theme_settings', {
				theme: theme.name,
				[field.fieldname]: field.value,
			});
		}
	}

	test('Saving a theme setting re-renders the preview once', async ({
		page,
	}) => {
		await saveThemeSetting(page, async () => {});
	});

	test('Saving a theme setting shows the new value in the preview https://github.com/bwhtech/commera/issues/607', async ({
		page,
	}) => {
		test.fail();
		await saveThemeSetting(page, async (changed) => {
			await expect
				.poll(() =>
					page
						.locator('iframe[data-preview-frame="visible"]')
						.evaluate(
							(frame) =>
								(frame as HTMLIFrameElement).contentDocument?.documentElement
									.outerHTML ?? '',
						),
				)
				.toContain(changed);
		});
	});

	test('A new section made only of blocks says how to add its first block', async ({
		page,
	}) => {
		const editorData = await api.get<LayoutEditor>(
			'commera.api.admin.theme_layout.get_editor',
			{ theme: theme.name, page: 'index' },
		);
		const schema = editorData.section_schemas.find(
			(candidate) =>
				(candidate.groups ?? ['pages']).includes('pages') &&
				!candidate.settings?.length &&
				Object.keys(candidate.blocks ?? {}).length,
		);
		test.skip(
			!schema,
			'this theme has no home page section made only of blocks',
		);
		if (!schema) return;
		await openEditor(page, theme);

		await addSection(page, schema.type);
		await expect(settingsPanel(page)).toBeVisible();
		try {
			const panel = await settingsPanel(page).innerText();
			const blockName = Object.values(schema.blocks ?? {})[0].name;
			expect(panel, `the panel says "${panel.replace(/\s+/g, ' ')}"`).toContain(
				`Add a ${blockName}`,
			);
			expect(panel, 'it does not point the merchant at dragging').not.toContain(
				'Drag it in the list',
			);
		} finally {
			await page
				.locator('[data-settings-panel] button[aria-label="Remove section"]')
				.click();
		}
	});

	test('A theme that is not active is never called live', async ({ page }) => {
		const data = await api.get<EditorData>(
			'commera.api.admin.theme.get_editor_data',
		);
		const inactive = data.themes.find(
			(candidate) => !candidate.live && candidate.theme_type === 'Sections',
		);
		test.skip(!inactive, 'every Sections theme is live');
		if (!inactive) return;
		await openEditor(page, inactive);
		const header = await page.locator('header').first().innerText();
		expect(
			/\bLive\b/.test(header),
			`the header says "${header.replace(/\s+/g, ' ')}"`,
		).toBe(false);
		expect(header, 'the badge says the theme is not live').toContain(
			'Not live',
		);
	});

	test('A refused theme settings save keeps what was typed', async ({
		page,
	}) => {
		await openEditor(page, theme);
		await openThemeSettings(page);
		const field = await firstTextThemeSetting(page);
		test.skip(!field, 'this theme has no text theme setting');
		if (!field) return;

		await page.route(
			(url) => url.href.includes('theme.save_theme_settings'),
			(route) => route.fulfill(REFUSAL),
		);

		const save = saveSettingsButton(page);
		await expect(save, 'Save is off until something changes').toBeDisabled();
		await page.locator(`#${field.id}`).click();
		await page.keyboard.press('End');
		await page.keyboard.type(' refused');
		await expect(save, 'Save turns on after a change').toBeEnabled();
		const refused = page.waitForResponse((response) =>
			response.url().includes('theme.save_theme_settings'),
		);
		await save.click();
		await refused;
		await page.waitForTimeout(500);
		await expect(page.locator(`#${field.id}`)).toHaveValue(
			`${field.value} refused`,
		);
		await expect(
			save,
			'Save stays on so the change can be retried',
		).toBeEnabled();
	});

	test('The tree resizes, never folds away, and keeps its size after a reload', async ({
		page,
	}) => {
		await openEditor(page, theme, { clearWorkspace: true });

		const treeWidth = await panelWidth(page, 'tree');
		await dragBy(page, '[data-editor-handle="tree"]', 80);
		await expect
			.poll(async () =>
				Math.abs((await panelWidth(page, 'tree')) - treeWidth - 80),
			)
			.toBeLessThanOrEqual(4);
		const widened = await panelWidth(page, 'tree');

		await dragBy(page, '[data-editor-handle="tree"]', -600);
		await expect
			.poll(async () => Math.abs((await panelWidth(page, 'tree')) - 220), {
				message:
					'a hard drag stops at the minimum, it never folds the tree away',
			})
			.toBeLessThanOrEqual(2);
		await dragBy(page, '[data-editor-handle="tree"]', widened - 220);
		await expect.poll(() => panelWidth(page, 'tree')).toBe(widened);

		expect(
			await panelWidth(page, 'settings'),
			'with nothing selected there is no settings column',
		).toBe(0);
		await openThemeSettings(page);
		await clickButton(page, 'Close theme settings');
		await expect(
			page.locator('[data-theme-settings-panel]'),
			'theme settings close at once',
		).toHaveCount(0);
		await expect
			.poll(() => panelWidth(page, 'settings'), {
				message: 'closing with nothing selected folds the column away',
			})
			.toBe(0);
		await firstSection(page).click();
		await expect
			.poll(() => panelWidth(page, 'settings'), {
				message: 'selecting a section opens its settings',
			})
			.toBeGreaterThan(0);
		await openThemeSettings(page);
		await clickButton(page, 'Close theme settings');
		await expect(
			settingsPanel(page),
			'closing goes back to the section that was selected',
		).toBeVisible();

		await page.reload({ waitUntil: 'networkidle' });
		await expect(firstSection(page)).toBeVisible({ timeout: 30000 });
		await expect.poll(() => panelWidth(page, 'tree')).toBe(widened);
		expect(
			await panelWidth(page, 'settings'),
			'a reload starts with nothing selected',
		).toBe(0);
	});

	test('The preview fits the canvas, scrolls its own page and maximises', async ({
		page,
	}) => {
		await openEditor(page, theme, { clearWorkspace: true });

		const canvas = await box(page, '[data-preview-canvas]');
		const fit = await previewScale(page);
		const frameBefore = await box(page, frameSelector('desktop'));
		expect(fit > 0.1 && fit <= 1, `fit is ${fit}`).toBe(true);
		expect(
			frameBefore.x >= canvas.x &&
				frameBefore.x + frameBefore.width <= canvas.x + canvas.width + 1,
			'fit keeps the desktop frame inside the canvas',
		).toBe(true);
		expect(
			frameBefore.y + frameBefore.height <= canvas.y + canvas.height,
			'the frame ends inside the canvas',
		).toBe(true);

		const scrolledBefore = await inFrame(
			page,
			'desktop',
			(iframe) => iframe.contentWindow?.scrollY,
		);
		await wheelOver(page, 'desktop');
		await expect
			.poll(
				() =>
					inFrame(page, 'desktop', (iframe) => iframe.contentWindow?.scrollY),
				{ message: 'the wheel scrolls the storefront page' },
			)
			.toBeGreaterThan(scrolledBefore);
		expect(
			await box(page, frameSelector('desktop')),
			'the frame does not move',
		).toEqual(frameBefore);

		await setZoom(page, '1', 1);
		await setZoom(page, '0.75', 0.75);
		await setZoom(page, 'fit', fit);

		const treeWidth = await panelWidth(page, 'tree');
		await clickButton(page, 'Maximise preview');
		await expect.poll(() => panelWidth(page, 'tree')).toBe(0);
		expect(await panelWidth(page, 'settings')).toBe(0);
		await page.keyboard.press('Escape');
		await expect.poll(() => panelWidth(page, 'tree')).toBe(treeWidth);
		await clickButton(page, 'Maximise preview');
		await clickButton(page, 'Restore panels');
		await expect.poll(() => panelWidth(page, 'tree')).toBe(treeWidth);
	});

	test('Desktop and mobile previews side by side both follow the selection', async ({
		page,
	}) => {
		await openEditor(page, theme, { clearWorkspace: true });

		await pickPreviewOption(page, 'Desktop and mobile');
		await expect(page.locator(frameSelector('mobile'))).toBeVisible({
			timeout: 30000,
		});
		await expect
			.poll(() =>
				inFrame(page, 'desktop', (iframe) => iframe.contentWindow?.innerWidth),
			)
			.toBe(1280);
		await expect
			.poll(() =>
				inFrame(page, 'mobile', (iframe) => iframe.contentWindow?.innerWidth),
			)
			.toBe(390);

		const canvas = await box(page, '[data-preview-canvas]');
		const desktopBox = await box(page, '[data-preview-device="desktop"]');
		const mobileBox = await box(page, '[data-preview-device="mobile"]');
		expect(
			desktopBox.x >= canvas.x &&
				mobileBox.x + mobileBox.width <= canvas.x + canvas.width + 1,
			'both frames fit',
		).toBe(true);

		const desktopScroll = await inFrame(
			page,
			'desktop',
			(iframe) => iframe.contentWindow?.scrollY,
		);
		await wheelOver(page, 'mobile');
		await expect
			.poll(
				() =>
					inFrame(page, 'mobile', (iframe) => iframe.contentWindow?.scrollY),
				{ message: 'the mobile page scrolls' },
			)
			.toBeGreaterThan(0);
		expect(
			await inFrame(page, 'desktop', (iframe) => iframe.contentWindow?.scrollY),
			'the desktop page stays where it was',
		).toBe(desktopScroll);

		await firstSection(page).click();
		await expect
			.poll(() => outlineShown(page, 'desktop'), {
				message: 'desktop highlights the picked section',
			})
			.toBe(true);
		await expect
			.poll(() => outlineShown(page, 'mobile'), {
				message: 'mobile highlights the picked section',
			})
			.toBe(true);

		const picked = await inFrame(page, 'mobile', (iframe) => {
			const sections = iframe.contentDocument?.querySelectorAll<HTMLElement>(
				'[data-commera-section]',
			);
			const section = sections[sections.length - 1];
			section.click();
			return section.dataset.commeraSection ?? '';
		});
		const selected = page
			.locator('[data-tree-node][aria-current="true"]')
			.first();
		await expect
			.poll(async () => (await selected.getAttribute('data-tree-node')) ?? '', {
				message: `a click in the mobile preview selects ${picked}`,
			})
			.toContain(picked);
		await expect
			.poll(() => outlineShown(page, 'desktop'), {
				message: 'the desktop preview follows a pick made on mobile',
			})
			.toBe(true);
	});

	test('Desktop and mobile previews keep the same section at the top', async ({
		page,
	}) => {
		await openEditor(page, theme, { clearWorkspace: true });

		const target = await page
			.locator('[data-tree-node^="section:index:"]')
			.evaluateAll((nodes) => {
				const deals = (nodes as HTMLElement[]).find((node) =>
					node.innerText.trim().startsWith('Deals'),
				);
				return (deals ?? (nodes as HTMLElement[])[nodes.length - 2])?.dataset
					.treeNode;
			});
		test.skip(!target, 'the home page has too few sections to scroll between');
		if (!target) return;
		const [, group, section] = target.split(':');

		await pickPreviewOption(page, 'Desktop and mobile');
		await expect(page.locator(frameSelector('mobile'))).toBeVisible({
			timeout: 30000,
		});
		const selector = { group, section };
		const sectionTop = (device: string) =>
			inFrame(
				page,
				device,
				(iframe, { group, section }) =>
					iframe.contentDocument
						?.querySelector(
							`[data-commera-group="${group}"][data-commera-section="${section}"]`,
						)
						?.getBoundingClientRect().top,
				selector,
			);

		await page.waitForTimeout(1000);
		await inFrame(
			page,
			'desktop',
			(iframe, { group, section }) => {
				const element = iframe.contentDocument?.querySelector(
					`[data-commera-group="${group}"][data-commera-section="${section}"]`,
				);
				if (!element || !iframe.contentWindow) return;
				iframe.contentWindow.scrollTo({
					top:
						element.getBoundingClientRect().top + iframe.contentWindow.scrollY,
					behavior: 'instant',
				});
			},
			selector,
		);
		await expect
			.poll(async () => Math.abs(await sectionTop('desktop')), {
				message: `desktop shows ${section} at the top`,
			})
			.toBeLessThanOrEqual(2);
		await expect
			.poll(async () => Math.abs(await sectionTop('mobile')), {
				message: `mobile follows to ${section}`,
			})
			.toBeLessThanOrEqual(2);
	});

	test('Typing Arabic over a default text keeps the English default', async ({
		page,
	}) => {
		const editorData = await api.get<LayoutEditor>(
			'commera.api.admin.theme_layout.get_editor',
			{ theme: theme.name, page: 'index' },
		);
		const schema = editorData.section_schemas.find(
			(candidate) =>
				(candidate.groups ?? ['pages']).includes('pages') &&
				candidate.settings?.some(
					(setting) => setting.type === 'text' && setting.default,
				),
		);
		test.skip(
			!schema,
			'no home page section has a text setting with a default',
		);
		const setting = schema?.settings?.find(
			(candidate) => candidate.type === 'text' && candidate.default,
		);
		if (!schema || !setting) return;

		const languages = await api.get<{ languages: Array<{ code: string }> }>(
			'commera.api.admin.storefront_languages.get_storefront_languages',
		);
		const addedArabic = !languages.languages.some(
			(language) => language.code === 'ar',
		);
		if (addedArabic) {
			await api.post(
				'commera.api.admin.storefront_languages.add_storefront_language',
				{ language: 'ar', published: 1 },
			);
		}
		try {
			await typeArabicOverDefault(page, schema.type, setting);
		} finally {
			if (addedArabic) {
				await api.post(
					'commera.api.admin.storefront_languages.remove_storefront_language',
					{ language: 'ar' },
				);
			}
		}
	});

	async function typeArabicOverDefault(
		page: Page,
		sectionType: string,
		setting: { id: string; default?: unknown },
	) {
		await openEditor(page, theme);

		await addSection(page, sectionType);
		const input = page.locator(`[data-settings-panel] #setting-${setting.id}`);
		await expect(input).toBeVisible();

		try {
			await pickPreviewOption(page, 'Right to left');
			await input.click();
			await page.keyboard.type('عرض خاص');
			await page.keyboard.press('Tab');
			await pickPreviewOption(page, 'Left to right');
			await expect(input).toHaveValue(setting.default as string);
		} finally {
			await pickPreviewOption(page, 'Left to right');
			await page
				.locator('[data-settings-panel] button[aria-label="Remove section"]')
				.click();
		}
	}

	test('Switching page keeps unsaved theme settings, and leaving asks about them', async ({
		page,
	}) => {
		const home = await api.get<LayoutEditor>(
			'commera.api.admin.theme_layout.get_editor',
			{ theme: theme.name, page: 'index' },
		);
		const pages = home.pages.includes('product')
			? home.pages
			: [...home.pages, 'product'];
		await page.route(
			(url) => url.pathname.endsWith('theme_layout.get_editor'),
			async (route) => {
				const request = route.request();
				const url = new URL(request.url());
				const asked =
					JSON.parse(request.postData() || '{}').page ??
					url.searchParams.get('page');
				if (asked !== 'index' && asked !== 'product') return route.continue();
				return route.fulfill({
					status: 200,
					contentType: 'application/json',
					body: JSON.stringify({ data: { ...home, pages, page: asked } }),
				});
			},
		);

		await openEditor(page, theme);
		await openThemeSettings(page);

		const field = await firstTextThemeSetting(page);
		test.skip(!field, 'this theme has no editable text setting');
		if (!field) return;
		const typed = `${field.value} E2E unsaved`;
		const input = page.locator(`#${field.id}`);
		await input.click();
		await input.selectText();
		await page.keyboard.type(typed);

		const editorHeaderButtons = page.locator(
			'[data-theme-layout-editor] header button',
		);
		await editorHeaderButtons
			.filter({ has: page.locator('.lucide-chevron-down') })
			.first()
			.click();
		const option = page
			.locator('[role=menuitem]')
			.filter({ hasText: /^\s*Product/ })
			.first();
		await expect(
			option,
			'the page picker offers no Product page',
		).toBeVisible();
		await option.click();
		await expect(
			editorHeaderButtons.filter({ hasText: /^\s*Product/ }).first(),
		).toBeVisible({ timeout: 15000 });
		await page.waitForTimeout(800);
		await expect(
			input,
			'a page switch dropped the typed theme setting',
		).toHaveValue(typed);

		await page
			.locator(
				'[data-theme-layout-editor] header nav a, [data-theme-layout-editor] header a',
			)
			.first()
			.click();
		await expect(page.locator('body')).toContainText(
			'Discard unsaved theme settings?',
			{ timeout: 5000 },
		);
		await page
			.locator('[role=dialog] button')
			.filter({ hasText: exactText('Cancel') })
			.first()
			.click();
		await page.waitForTimeout(600);
		expect(page.url(), 'Cancel did not keep the editor open').toContain(
			'/editor',
		);
	});
});
