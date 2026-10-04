import assert from 'node:assert/strict';
import {
	existsSync,
	mkdirSync,
	mkdtempSync,
	readFileSync,
	rmSync,
	symlinkSync,
	writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, describe, test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import commera from '../vite.js';

// The kit installs nothing of its own; the dashboard's node_modules carries the vite and vue it builds with.
const here = dirname(fileURLToPath(import.meta.url));
const dashboardModules = join(here, '../../../dashboard/node_modules');
const vitePackage = join(dashboardModules, 'vite');
const { build } = await import(
	pathToFileURL(
		join(
			vitePackage,
			JSON.parse(readFileSync(join(vitePackage, 'package.json'), 'utf8'))
				.exports['.'].import.default,
		),
	).href
);

const APP = 'fixture_app';
const workspace = mkdtempSync(join(tmpdir(), 'commera-kit-'));
after(() => rmSync(workspace, { recursive: true, force: true }));

const hostDir = join(workspace, 'host');
mkdirSync(hostDir);
writeFileSync(
	join(hostDir, 'icons.json'),
	JSON.stringify(['printer', 'gift', 'rotate-cw']),
);
writeFileSync(
	join(hostDir, 'classes.json'),
	JSON.stringify(['p-2', 'text-ink-gray-7']),
);
writeFileSync(
	join(hostDir, 'shared-exports.json'),
	JSON.stringify({
		vue: Object.keys(
			await import(pathToFileURL(join(dashboardModules, 'vue/index.mjs')).href),
		),
		'frappe-ui': ['Button', 'Dialog', 'dialog'],
		'frappe-ui/list': [],
		'@commera/admin': ['useExtension', 'usePage', 'useAction'],
	}),
);

let appCount = 0;

function makeApp(files) {
	const root = join(workspace, `app-${appCount++}`, APP);
	mkdirSync(root, { recursive: true });
	writeFileSync(
		join(root, 'package.json'),
		'{"name":"fixture","private":true}',
	);
	symlinkSync(dashboardModules, join(root, 'node_modules'), 'dir');
	for (const [path, source] of Object.entries(files)) {
		const file = join(root, 'commera', path);
		mkdirSync(dirname(file), { recursive: true });
		writeFileSync(file, source);
	}
	return root;
}

async function buildApp(files) {
	const root = makeApp(files);
	await build({
		configFile: false,
		logLevel: 'silent',
		// An inline config stops Vite searching for one after the test has deleted the folder.
		css: { postcss: {} },
		plugins: [commera({ root, app: APP, hostDir })],
	});
	const outDir = join(root, APP, 'public', 'commera');
	return {
		outDir,
		manifest: JSON.parse(readFileSync(join(outDir, 'manifest.json'), 'utf8')),
		read: (path) => readFileSync(join(outDir, path), 'utf8'),
	};
}

async function buildFails(files, pattern) {
	await assert.rejects(buildApp(files), (error) => {
		assert.match(error.message, pattern);
		return true;
	});
}

const vue = (
	extension,
	body = '<template><div class="p-2">hi</div></template>',
) => `<script>\nexport const extension = ${extension}\n</script>\n${body}\n`;

const page = vue(`{ label: 'Print jobs', icon: 'printer' }`);

describe('folder grammar', () => {
	test('a typo in a placement folder fails and lists the valid places', async () => {
		await buildFails(
			{ 'ordr/cards/status/index.vue': vue(`{ label: 'Status' }`) },
			/ordr\/cards\/status\/index\.vue declares an extension but ordr\/cards isn't a Commera placement; valid places:[\s\S]*order\/cards\/<name>\/index\.vue/,
		);
	});

	test('a placement one level too deep with an extension block fails', async () => {
		await buildFails(
			{ 'pages/jobs/detail/index.vue': page },
			/pages\/jobs\/detail\/index\.vue declares an extension but pages\/jobs isn't a Commera placement/,
		);
	});

	test('helper folders and sibling components without a block are left alone', async () => {
		const { manifest } = await buildApp({
			'pages/jobs/index.vue': page,
			'pages/jobs/JobList.vue':
				'<template><div class="p-2">list</div></template>',
			'pages/jobs/detail/index.vue':
				'<template><div class="p-2">detail</div></template>',
			'shared/pill/index.vue':
				'<template><span class="p-2">pill</span></template>',
			'components/StatusPill.vue':
				'<template><span class="p-2">pill</span></template>',
		});
		assert.deepEqual(
			manifest.extensions.map((entry) => `${entry.place}/${entry.name}`),
			['pages/jobs'],
		);
	});

	test('a sibling component may not declare an extension', async () => {
		await buildFails(
			{ 'pages/jobs/index.vue': page, 'pages/jobs/JobList.vue': page },
			/pages\/jobs\/JobList\.vue declares an extension, but only a placement's index\.vue may/,
		);
	});

	test('a reserved folder warns and is not built', async () => {
		const { manifest, outDir } = await buildApp({
			'pages/jobs/index.vue': page,
			'orders/selection/bulk/index.vue': vue(`{ label: 'Bulk' }`),
		});
		assert.equal(manifest.extensions.length, 1);
		assert.equal(existsSync(join(outDir, 'orders')), false);
	});

	test('a bad slug fails', async () => {
		await buildFails(
			{ 'pages/Print_Jobs/index.vue': page },
			/'Print_Jobs' must be lowercase/,
		);
	});

	test('an index.vue at a placement without a block fails', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': '<template><div class="p-2">x</div></template>',
			},
			/pages\/jobs\/index\.vue: add `<script>export const extension/,
		);
	});

	test('every problem is reported in one build', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': vue(`{ label: 'Jobs' }`),
				'order/cards/status/index.vue': vue(
					`{ label: 'Status', sidebar: true }`,
				),
			},
			/2 problems[\s\S]*extension\.sidebar is not allowed on order\/cards[\s\S]*extension\.icon is required/,
		);
	});
});

describe('the extension block is literal only', () => {
	for (const [kind, value, path] of [
		['a call', `{ label: label(), icon: 'printer' }`, 'extension.label'],
		['an identifier', `{ label: LABEL, icon: 'printer' }`, 'extension.label'],
		['a spread', `{ ...base, label: 'x', icon: 'printer' }`, 'extension'],
		[
			'a template with an expression',
			"{ label: `x${1}`, icon: 'printer' }",
			'extension.label',
		],
	]) {
		test(`${kind} fails with its position`, async () => {
			await buildFails(
				{ 'pages/jobs/index.vue': vue(value) },
				new RegExp(
					`pages/jobs/index\\.vue:2:\\d+ ${path.replace(
						'.',
						'\\.',
					)} must be a literal`,
				),
			);
		});
	}

	test('a computed key fails', async () => {
		await buildFails(
			{ 'pages/jobs/index.vue': vue(`{ ['label']: 'x', icon: 'printer' }`) },
			/extension keys must be plain names/,
		);
	});

	test('an extra import in the plain script fails', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': `<script>\nimport { x } from './x.js'\nexport const extension = { label: 'Jobs', icon: 'printer' }\n</script>\n<template><div class="p-2" /></template>\n`,
			},
			/index\.vue:2:1 the plain <script> may only hold `export const extension/,
		);
	});
});

describe('schema per placement', () => {
	test('an unknown key suggests the right one', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': vue(
					`{ label: 'Jobs', icon: 'printer', sidebr: false }`,
				),
			},
			/extension\.sidebr is not allowed on pages \(did you mean 'sidebar'\?\)/,
		);
	});

	test('a missing label fails', async () => {
		await buildFails(
			{ 'order/cards/status/index.vue': vue('{ order: 1 }') },
			/order\/cards\/status\/index\.vue: extension\.label is required/,
		);
	});

	test('an action with both a template and a method fails', async () => {
		await buildFails(
			{
				'order/actions/resend/index.vue': vue(
					`{ label: 'Resend', method: '${APP}.api.resend' }`,
				),
			},
			/has both a template and extension\.method; keep exactly one/,
		);
	});

	test('an action with neither a template nor a method fails', async () => {
		await buildFails(
			{
				'order/actions/resend/index.vue':
					"<script>\nexport const extension = { label: 'Resend' }\n</script>\n",
			},
			/needs either a template or extension\.method; it has neither/,
		);
	});

	test('settings with both a template and a doctype fails', async () => {
		await buildFails(
			{
				'settings/index.vue': vue(
					`{ label: 'Gift wrap', doctype: 'Gift Wrap Settings' }`,
				),
			},
			/has both a template and extension\.doctype/,
		);
	});

	test('settings with neither fails', async () => {
		await buildFails(
			{
				'settings/index.vue':
					"<script>\nexport const extension = { label: 'Gift wrap' }\n</script>\n",
			},
			/needs either a template or extension\.doctype/,
		);
	});

	const command = (extension) =>
		`<script>\nexport const extension = ${extension}\n</script>\n`;

	test('a command with a template fails', async () => {
		await buildFails(
			{
				'commands/sync/index.vue': vue(
					`{ label: 'Sync', method: '${APP}.api.sync' }`,
				),
			},
			/commands\/sync\/index\.vue: can't have a <template> or <script setup>; commands is declared by the extension block alone/,
		);
	});

	test('a command without a method fails', async () => {
		await buildFails(
			{ 'commands/sync/index.vue': command(`{ label: 'Sync' }`) },
			/commands\/sync\/index\.vue: extension\.method is required/,
		);
	});

	for (const [problem, keywords] of [
		['a plain string', `'sync'`],
		['an empty list', '[]'],
		['a blank word', `['sync', ' ']`],
	]) {
		test(`command keywords as ${problem} fail`, async () => {
			await buildFails(
				{
					'commands/sync/index.vue': command(
						`{ label: 'Sync', method: '${APP}.api.sync', keywords: ${keywords} }`,
					),
				},
				/extension\.keywords must be a list of non-empty text/,
			);
		});
	}

	test('an icon outside the list fails with a suggestion', async () => {
		await buildFails(
			{ 'pages/jobs/index.vue': vue(`{ label: 'Jobs', icon: 'printr' }`) },
			/'printr' is not a Commera icon \(did you mean 'printer'\?\)/,
		);
	});

	test('a dotted path outside the app fails', async () => {
		await buildFails(
			{
				'order/cards/status/index.vue': vue(
					`{ label: 'Status', condition: 'frappe.client.get_list' }`,
				),
			},
			/extension\.condition 'frappe\.client\.get_list' must start with 'fixture_app\.'/,
		);
	});
});

describe('guards', () => {
	test('a style block fails', async () => {
		await buildFails(
			{ 'pages/jobs/index.vue': `${page}<style>.x { color: red }</style>\n` },
			/app pages ship no CSS/,
		);
	});

	test('a class the dashboard does not ship fails', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': vue(
					`{ label: 'Jobs', icon: 'printer' }`,
					'<template><div class="p-13" /></template>',
				),
			},
			/classes the dashboard does not ship: p-13/,
		);
	});

	test('an unshared subpath fails', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': `${page}<script setup>\nimport { AxisChart } from 'frappe-ui/charts'\nconsole.log(AxisChart)\n</script>\n`,
			},
			/import 'frappe-ui\/charts' is not shared with app pages/,
		);
	});

	test('a name the dashboard does not share fails', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': `${page}<script setup>\nimport { Foo } from 'frappe-ui'\nconsole.log(Foo)\n</script>\n`,
			},
			/'frappe-ui' does not share Foo with app pages/,
		);
	});

	test('a missing @commera/admin name says the dashboard build may be stale', async () => {
		await buildFails(
			{
				'pages/jobs/index.vue': `${page}<script setup>\nimport { useLater } from '@commera/admin'\nconsole.log(useLater)\n</script>\n`,
			},
			/'@commera\/admin' does not share useLater with app pages \(or .* is from an older Commera: rebuild it with `bench build --app commera`\)/,
		);
	});

	for (const name of ['AppPageHeader', 'PageBody', 'ExtensionCard']) {
		test(`importing ${name} fails because the dashboard does not share it`, async () => {
			await buildFails(
				{
					'pages/jobs/index.vue': `${page}<script setup>\nimport { ${name} } from '@commera/admin'\nconsole.log(${name})\n</script>\n`,
				},
				new RegExp(`'@commera/admin' does not share ${name} with app pages`),
			);
		});
	}

	for (const [name, specifier, hint] of [
		['Dialog', 'frappe-ui', /useAction\(\)/],
	]) {
		test(`importing ${name} fails and points at the host`, async () => {
			await buildFails(
				{
					'pages/jobs/index.vue': `${page}<script setup>\nimport { ${name} } from '${specifier}'\nconsole.log(${name})\n</script>\n`,
				},
				new RegExp(
					`do not import ${name} from '${specifier}'[\\s\\S]*${hint.source}`,
				),
			);
		});
	}

	for (const name of ['createResource', 'useCall', 'useList', 'call']) {
		test(`importing ${name} from frappe-ui fails and points at useMethodRead`, async () => {
			await assert.rejects(
				buildApp({
					'pages/jobs/index.vue': `${page}<script setup>\nimport { ${name} } from 'frappe-ui'\nconsole.log(${name})\n</script>\n`,
				}),
				(error) => {
					assert.match(
						error.message,
						new RegExp(
							`${name} calls Frappe's v1 API, which this dashboard reads as null\\. Use useMethodRead / useMethodAction with a whitelisted method in your app's api\\.py\\.`,
						),
					);
					assert.doesNotMatch(error.message, /does not share/);
					return true;
				},
			);
		});
	}

	test('a Dialog in shared code fails too', async () => {
		await buildFails(
			{
				'order/actions/resend/index.vue': vue(
					`{ label: 'Resend' }`,
					`<template><div class="p-2" /></template>\n<script setup>\nimport { open } from '../../../shared/open.js'\nopen()\n</script>`,
				),
				'shared/open.js': `import { Dialog } from 'frappe-ui'\nexport const open = () => console.log(Dialog)\n`,
			},
			/do not import Dialog from 'frappe-ui'/,
		);
	});
});

describe('a clean build', () => {
	test('the manifest covers every placement and the shipped JS keeps no dotted path', async () => {
		const card = (label) =>
			vue(
				`{ label: '${label}', condition: '${APP}.conditions.has_jobs', requires: 'POD Job', order: 2 }`,
				'<template><div class="p-2">card</div></template>',
			);
		const { manifest, read } = await buildApp({
			'pages/jobs/index.vue': vue(
				`{ label: 'Print jobs', icon: 'printer', order: 1, sidebar: true, requires: 'POD Job' }`,
			),
			'pages/provider-orders/index.vue': vue(
				`{ label: 'Provider orders', icon: 'printer', sidebar: false, order: -1 }`,
			),
			'order/cards/print-status/index.vue': card('Print status'),
			'product/cards/listing/index.vue': card('Listing'),
			'customer/cards/points/index.vue': card('Points'),
			'order/actions/resend/index.vue': `<script>\nexport const extension = { label: 'Resend to printer', icon: 'rotate-cw', method: '${APP}.api.resend_order', confirm: \`Send this order's print jobs again?\` }\n</script>\n`,
			'order/actions/pick/index.vue': vue(
				`{ label: 'Pick a printer', icon: 'printer' }`,
			),
			'product/actions/sync/index.vue': `<script>\nexport const extension = { label: 'Sync now', method: '${APP}.api.sync' }\n</script>\n`,
			'customer/actions/award/index.vue': vue(
				`{ label: 'Award points', icon: 'gift' }`,
			),
			'settings/index.vue':
				"<script>\nexport const extension = { label: 'Gift wrap', icon: 'gift', doctype: 'Gift Wrap Settings' }\n</script>\n",
		});

		assert.equal(manifest.api_version, 1);
		assert.equal(manifest.kit_version, '0.2.0');
		assert.equal(manifest.app, APP);
		const hashes = manifest.extensions.map((entry) => entry.hash);
		for (const [index, hash] of hashes.entries()) {
			if (manifest.extensions[index].module)
				assert.match(hash, /^[0-9a-f]{8}$/);
		}
		const shape = manifest.extensions.map(({ hash, ...entry }) => entry);
		assert.deepEqual(shape, [
			{
				place: 'customer/actions',
				name: 'award',
				module: 'customer/actions/award.js',
				label: 'Award points',
				icon: 'gift',
			},
			{
				place: 'customer/cards',
				name: 'points',
				module: 'customer/cards/points.js',
				label: 'Points',
				requires: 'POD Job',
				condition: `${APP}.conditions.has_jobs`,
				order: 2,
			},
			{
				place: 'order/actions',
				name: 'pick',
				module: 'order/actions/pick.js',
				label: 'Pick a printer',
				icon: 'printer',
			},
			{
				place: 'order/actions',
				name: 'resend',
				module: null,
				label: 'Resend to printer',
				icon: 'rotate-cw',
				method: `${APP}.api.resend_order`,
				confirm: "Send this order's print jobs again?",
			},
			{
				place: 'order/cards',
				name: 'print-status',
				module: 'order/cards/print-status.js',
				label: 'Print status',
				requires: 'POD Job',
				condition: `${APP}.conditions.has_jobs`,
				order: 2,
			},
			{
				place: 'pages',
				name: 'jobs',
				module: 'pages/jobs.js',
				label: 'Print jobs',
				icon: 'printer',
				requires: 'POD Job',
				sidebar: true,
				order: 1,
			},
			{
				place: 'pages',
				name: 'provider-orders',
				module: 'pages/provider-orders.js',
				label: 'Provider orders',
				icon: 'printer',
				sidebar: false,
				order: -1,
			},
			{
				place: 'product/actions',
				name: 'sync',
				module: null,
				label: 'Sync now',
				method: `${APP}.api.sync`,
			},
			{
				place: 'product/cards',
				name: 'listing',
				module: 'product/cards/listing.js',
				label: 'Listing',
				requires: 'POD Job',
				condition: `${APP}.conditions.has_jobs`,
				order: 2,
			},
			{
				place: 'settings',
				name: 'settings',
				module: null,
				label: 'Gift wrap',
				icon: 'gift',
				doctype: 'Gift Wrap Settings',
			},
		]);

		const cardModule = read('order/cards/print-status.js');
		assert.ok(cardModule.startsWith('/* commera-extension-api: 1 */\n'));
		assert.doesNotMatch(cardModule, /has_jobs|POD Job|Print status/);
		assert.doesNotMatch(read('pages/jobs.js'), /Print jobs/);
	});

	test('an app with only declarative entries emits just the manifest', async () => {
		const { manifest, outDir } = await buildApp({
			'settings/index.vue':
				"<script>\nexport const extension = { label: 'Gift wrap', doctype: 'Gift Wrap Settings' }\n</script>\n",
		});
		assert.equal(manifest.extensions[0].module, null);
		assert.equal(existsSync(join(outDir, '__empty.js')), false);
	});

	test('a command reaches the manifest with its keywords and no module', async () => {
		const { manifest } = await buildApp({
			'commands/sync/index.vue': `<script>\nexport const extension = { label: 'Sync', icon: 'rotate-cw', keywords: ['print', 'orders'], method: '${APP}.api.sync' }\n</script>\n`,
		});
		assert.deepEqual(manifest.extensions, [
			{
				place: 'commands',
				name: 'sync',
				module: null,
				hash: null,
				label: 'Sync',
				icon: 'rotate-cw',
				keywords: ['print', 'orders'],
				method: `${APP}.api.sync`,
			},
		]);
	});
});

describe('the app icon', () => {
	const svg =
		'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><defs><path id="a" d="M0 0h24v24H0z"/></defs><use href="#a"/></svg>\n';

	test('a valid icon.svg is copied next to the manifest and named in it', async () => {
		const { manifest, read } = await buildApp({
			'pages/jobs/index.vue': page,
			'icon.svg': svg,
		});
		assert.equal(manifest.icon, 'icon.svg');
		assert.equal(read('icon.svg'), svg);
	});

	test('without an icon.svg the manifest has no icon', async () => {
		const { manifest, outDir } = await buildApp({
			'pages/jobs/index.vue': page,
		});
		assert.equal('icon' in manifest, false);
		assert.equal(existsSync(join(outDir, 'icon.svg')), false);
	});

	for (const [problem, source, pattern] of [
		[
			'a script',
			'<svg><script>alert(1)</script></svg>',
			/icon\.svg may not contain <script>/,
		],
		[
			'an event attribute',
			'<svg onload="alert(1)"></svg>',
			/icon\.svg may not use on\* event attributes/,
		],
		[
			'an external href',
			'<svg><image href="https://x.test/a.png"/></svg>',
			/icon\.svg may only link to its own #ids/,
		],
		[
			'an external xlink:href',
			"<svg><use xlink:href='other.svg#a'/></svg>",
			/icon\.svg may only link to its own #ids/,
		],
		[
			'another format',
			'<html><svg></svg></html>',
			/icon\.svg must be a single <svg> element/,
		],
		[
			'too many bytes',
			`<svg><!--${'x'.repeat(21 * 1024)}--></svg>`,
			/icon\.svg is 22 kB; keep it under 20 kB/,
		],
	]) {
		test(`an icon with ${problem} fails`, async () => {
			await buildFails(
				{ 'pages/jobs/index.vue': page, 'icon.svg': source },
				pattern,
			);
		});
	}
});
