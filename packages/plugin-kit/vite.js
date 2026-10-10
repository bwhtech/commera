import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';

const API_VERSION = 1;
const KIT_VERSION = JSON.parse(
	readFileSync(new URL('./package.json', import.meta.url), 'utf8'),
).version;
const GRAMMAR = JSON.parse(
	readFileSync(new URL('./places.json', import.meta.url), 'utf8'),
);
const BANNER = `/* commera-plugin-api: ${API_VERSION} */`;
const SHARED = [
	'vue',
	'frappe-ui',
	'frappe-ui/list',
	'frappe-ui/charts',
	'@commera/admin',
];
const SHARED_ROOTS = ['vue', 'frappe-ui', '@commera/admin'];
const STYLESHEET = /\.(css|scss|sass|less|styl|stylus|pcss|postcss)(\?|$)/;
const NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;
const DOTTED_PATH = /^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$/;
const EMPTY_ENTRY = '\0commera-empty-entry';
const EMPTY_ENTRY_PATH = '__commera_empty_entry__';
const PAGE_ENTRY = '\0commera-page:';
const PAGE_ENTRY_PATH = '__commera_page__/';
const DYNAMIC_FILE = /^\[(\.\.\.)?([^\]]*)\]\.vue$/;
const PARAM = /^[a-z][A-Za-z0-9]{0,39}$/;
const SKIPPED_DIRS = new Set(['node_modules', 'dist']);
const ICON_FILE = 'plugin-icon.svg';
const ICON_LIMIT = 20 * 1024;

const FRAPPE_V1 = new Set([
	'createResource',
	'createListResource',
	'createDocumentResource',
	'useCall',
	'useList',
	'useDoc',
	'useDoctype',
	'useNewDoc',
	'frappeRequest',
	'call',
]);

const FIELD_TYPES = {
	label: 'text',
	icon: 'icon',
	keywords: 'texts',
	requires: 'text',
	condition: 'dotted',
	method: 'dotted',
	confirm: 'text',
	doctype: 'text',
	sidebar: 'boolean',
	order: 'number',
};

const SLUG_HINT = '<name>';

function placementTable() {
	return Object.keys(GRAMMAR.places)
		.map((place) =>
			GRAMMAR.places[place].single
				? `  ${place}/index.vue`
				: `  ${place}/${SLUG_HINT}/index.vue`,
		)
		.join('\n');
}

function toPosix(path) {
	return path.split(sep).join('/');
}

function walk(dir, found = []) {
	for (const entry of readdirSync(dir, { withFileTypes: true })) {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) {
			if (!SKIPPED_DIRS.has(entry.name) && !entry.name.startsWith('.'))
				walk(path, found);
		} else if (entry.name.endsWith('.vue')) {
			found.push(path);
		}
	}
	return found;
}

// A `single` place is one slot named after itself; every other place takes one `<name>` folder.
function matchPlacement(folder) {
	if (GRAMMAR.places[folder]?.single) return { place: folder, name: folder };
	const cut = folder.lastIndexOf('/');
	if (cut < 0) return null;
	const place = folder.slice(0, cut);
	if (!GRAMMAR.places[place] || GRAMMAR.places[place].single) return null;
	return { place, name: folder.slice(cut + 1) };
}

function placeOf(folder) {
	const cut = folder.lastIndexOf('/');
	return cut < 0 ? folder : folder.slice(0, cut);
}

function isReserved(folder) {
	return GRAMMAR.reserved.some(
		(reserved) => folder === reserved || folder.startsWith(`${reserved}/`),
	);
}

function levenshtein(left, right) {
	const row = Array.from({ length: right.length + 1 }, (_, index) => index);
	for (let i = 1; i <= left.length; i++) {
		let diagonal = row[0];
		row[0] = i;
		for (let j = 1; j <= right.length; j++) {
			const above = row[j];
			row[j] = Math.min(
				row[j] + 1,
				row[j - 1] + 1,
				diagonal + (left[i - 1] === right[j - 1] ? 0 : 1),
			);
			diagonal = above;
		}
	}
	return row[right.length];
}

function suggest(word, candidates) {
	const [best] = candidates
		.map((candidate) => [candidate, levenshtein(word, candidate)])
		.sort((a, b) => a[1] - b[1]);
	return best && best[1] <= 2 ? ` (did you mean '${best[0]}'?)` : '';
}

class LiteralError extends Error {
	constructor(node, message) {
		super(message);
		this.node = node;
	}
}

function propertyKey(property) {
	if (property.computed) return null;
	if (property.key.type === 'Identifier') return property.key.name;
	if (property.key.type === 'StringLiteral') return property.key.value;
	return null;
}

function evaluateLiteral(node, path) {
	const fail = () => new LiteralError(node, `${path} must be a literal`);
	switch (node.type) {
		case 'StringLiteral':
		case 'NumericLiteral':
		case 'BooleanLiteral':
			return node.value;
		case 'NullLiteral':
			return null;
		case 'TemplateLiteral':
			if (node.expressions.length) throw fail();
			return node.quasis.map((quasi) => quasi.value.cooked).join('');
		case 'UnaryExpression':
			if (node.operator === '-' && node.argument.type === 'NumericLiteral')
				return -node.argument.value;
			throw fail();
		case 'ArrayExpression':
			return node.elements.map((element, index) => {
				if (!element || element.type === 'SpreadElement') throw fail();
				return evaluateLiteral(element, `${path}[${index}]`);
			});
		case 'ObjectExpression': {
			const value = {};
			for (const property of node.properties) {
				if (property.type !== 'ObjectProperty') throw fail();
				const key = propertyKey(property);
				if (key === null)
					throw new LiteralError(property, `${path} keys must be plain names`);
				value[key] = evaluateLiteral(property.value, `${path}.${key}`);
			}
			return value;
		}
		default:
			throw fail();
	}
}

function scriptPosition(script, node) {
	const { line, column } = node.loc.start;
	return line === 1
		? `${script.loc.start.line}:${script.loc.start.column + column}`
		: `${script.loc.start.line + line - 1}:${column + 1}`;
}

function parseScript(compiler, script) {
	const plugins = script.lang === 'ts' ? ['typescript'] : [];
	return compiler.babelParse(script.content, {
		sourceType: 'module',
		plugins,
	}).program.body;
}

function declaresPlugin(statement) {
	return (
		statement.type === 'ExportNamedDeclaration' &&
		statement.declaration?.type === 'VariableDeclaration' &&
		statement.declaration.declarations.some(
			(declarator) => declarator.id.name === 'plugin',
		)
	);
}

// Returns null when the SFC has no plain <script>, or a plain one that never mentions `plugin`.
function readPluginBlock(compiler, file, display) {
	const { descriptor, errors } = compiler.parse(readFileSync(file, 'utf8'), {
		filename: file,
	});
	if (errors.length)
		return {
			errors: errors.map((error) => `${display}: ${error.message}`),
			descriptor,
		};
	const script = descriptor.script;
	if (!script) return { descriptor, plugin: null, errors: [] };
	let body;
	try {
		body = parseScript(compiler, script);
	} catch (error) {
		return { descriptor, errors: [`${display}: ${error.message}`] };
	}
	if (!body.some(declaresPlugin))
		return { descriptor, plugin: null, errors: [] };
	const at = (node) => `${display}:${scriptPosition(script, node)}`;
	const strays = body.filter((statement) => !declaresPlugin(statement));
	const errorsFound = strays.map(
		(statement) =>
			`${at(
				statement,
			)} the plain <script> may only hold \`export const plugin = { … }\`; move other code to <script setup>`,
	);
	const statement = body.find(declaresPlugin);
	const { declaration } = statement;
	const [declarator] = declaration.declarations;
	if (
		declaration.kind !== 'const' ||
		declaration.declarations.length !== 1 ||
		declarator.init?.type !== 'ObjectExpression'
	) {
		errorsFound.push(
			`${at(statement)} write the block as \`export const plugin = { … }\``,
		);
		return { descriptor, plugin: null, errors: errorsFound, declared: true };
	}
	try {
		const plugin = evaluateLiteral(declarator.init, 'plugin');
		return { descriptor, plugin, errors: errorsFound, declared: true };
	} catch (error) {
		if (!(error instanceof LiteralError)) throw error;
		errorsFound.push(`${at(error.node)} ${error.message}`);
		return { descriptor, plugin: null, errors: errorsFound, declared: true };
	}
}

function checkField(key, value, { app, icons }) {
	switch (FIELD_TYPES[key]) {
		case 'text':
			return typeof value === 'string' && value.trim()
				? null
				: 'must be non-empty text';
		case 'texts':
			return Array.isArray(value) &&
				value.length &&
				value.every((text) => typeof text === 'string' && text.trim())
				? null
				: 'must be a list of non-empty text';
		case 'boolean':
			return typeof value === 'boolean' ? null : 'must be true or false';
		case 'number':
			return typeof value === 'number' && Number.isFinite(value)
				? null
				: 'must be a number';
		case 'icon':
			if (typeof value !== 'string') return 'must be an icon name';
			if (icons && !icons.includes(value))
				return `'${value}' is not a Commera icon${suggest(value, icons)}`;
			return null;
		case 'dotted':
			if (typeof value !== 'string' || !DOTTED_PATH.test(value))
				return 'must be a dotted path like my_app.module.function';
			return value.startsWith(`${app}.`)
				? null
				: `'${value}' must start with '${app}.'`;
		default:
			return null;
	}
}

function checkPlugin(plugin, place, { hasModule, hasTemplate }, context) {
	const spec = GRAMMAR.places[place];
	const problems = [];
	for (const [key, value] of Object.entries(plugin)) {
		if (!spec.fields.includes(key)) {
			problems.push(
				`plugin.${key} is not allowed on ${place}${suggest(key, spec.fields)}`,
			);
			continue;
		}
		const problem = checkField(key, value, context);
		if (problem) problems.push(`plugin.${key} ${problem}`);
	}
	for (const key of spec.required) {
		if (!(key in plugin)) problems.push(`plugin.${key} is required`);
	}
	const { declarative } = spec;
	// A sidebar action has no frame to draw into: its <script setup> runs when the row is clicked.
	if (spec.template === 'none' && hasTemplate)
		problems.push(
			`can't have a <template>; ${place} runs its <script setup> when the row is clicked`,
		);
	if (spec.module === 'required' && !hasModule)
		problems.push(
			spec.template === 'none'
				? 'needs a <script setup> to run when the row is clicked'
				: 'needs a <template> or <script setup>',
		);
	if (spec.module === 'none' && hasModule)
		problems.push(
			`can't have a <template> or <script setup>; ${place} is declared by the plugin block alone`,
		);
	if (spec.module === 'optional') {
		const declared = declarative in plugin;
		if (hasModule && declared)
			problems.push(
				`has both a template and plugin.${declarative}; keep exactly one`,
			);
		if (!hasModule && !declared)
			problems.push(
				`needs either a template or plugin.${declarative}; it has neither`,
			);
	}
	return problems;
}

export function discoverPlugins(
	sourceDir,
	{ app, compiler, icons = null, warn = () => {} },
) {
	const errors = [];
	const entries = [];
	const seen = new Map();
	const details = new Map();
	for (const file of walk(sourceDir).sort()) {
		const display = toPosix(relative(sourceDir, file));
		const isIndex = basename(file) === 'index.vue';
		const folder = toPosix(dirname(display));
		const placement = isIndex ? matchPlacement(folder) : null;
		const dynamic = basename(file).match(DYNAMIC_FILE);
		if (dynamic) {
			const [, rest, param] = dynamic;
			const problem = getDetailProblem(folder, rest, param, details);
			if (problem === 'reserved') {
				warn(
					`${display} is reserved for a later Commera; it was not built. Name it [...${param}].vue to get the rest of the URL`,
				);
				continue;
			}
			if (problem) errors.push(`${display}: ${problem}`);
			else details.set(folder, { file, param, display });
		}
		const block = readPluginBlock(compiler, file, display);

		if (!placement) {
			if (!block.declared) continue;
			if (isIndex && isReserved(folder)) {
				warn(`${display} is reserved for a later Commera; it was not built`);
				continue;
			}
			errors.push(
				isIndex
					? `${display} declares a plugin block but ${placeOf(
							folder,
						)} isn't a Commera placement; valid places:\n${placementTable()}`
					: `${display} declares a plugin block, but only a placement's index.vue may; valid places:\n${placementTable()}`,
			);
			continue;
		}

		errors.push(...block.errors);
		if (!block.declared) {
			errors.push(
				`${display}: add \`<script>export const plugin = { label: '…' }</script>\``,
			);
			continue;
		}
		if (!NAME.test(placement.name)) {
			errors.push(
				`${display}: '${placement.name}' must be lowercase letters, digits and hyphens (at most 40)`,
			);
			continue;
		}
		if (!block.plugin) continue;

		const { descriptor, plugin } = block;
		const hasModule = Boolean(descriptor.template || descriptor.scriptSetup);
		const problems = checkPlugin(
			plugin,
			placement.place,
			{ hasModule, hasTemplate: Boolean(descriptor.template) },
			{
				app,
				icons,
			},
		);
		errors.push(...problems.map((problem) => `${display}: ${problem}`));
		if (problems.length) continue;

		const key = `${placement.place}/${placement.name}`;
		if (seen.has(key)) {
			errors.push(`${display}: ${key} is already declared by ${seen.get(key)}`);
			continue;
		}
		seen.set(key, display);
		entries.push({
			place: placement.place,
			name: placement.name,
			file,
			entryName: hasModule
				? GRAMMAR.places[placement.place].single
					? placement.place
					: key
				: null,
			plugin,
		});
	}
	for (const [folder, detail] of details) {
		const entry = entries.find(
			(entry) => entry.place === 'pages' && `pages/${entry.name}` === folder,
		);
		if (entry) entry.detail = detail;
		else if (!existsSync(join(sourceDir, folder, 'index.vue')))
			errors.push(
				`${detail.display}: add ${folder}/index.vue; a detail page needs its list page`,
			);
	}
	return { entries, errors };
}

function getDetailProblem(folder, rest, param, details) {
	if (matchPlacement(folder)?.place !== 'pages')
		return 'only a page folder (pages/<name>/) may hold a [...param].vue';
	if (!rest) return 'reserved';
	if (!PARAM.test(param))
		return `'${param}' must be a camelCase prop name, such as [...id].vue`;
	if (details.has(folder))
		return `${folder} already has ${details.get(folder).display}`;
}

// The page stays mounted while its URL changes, so the detail is keyed by its id to load each record fresh.
export function pageEntryCode(entry) {
	const { file, param } = entry.detail;
	return [
		"import { defineComponent, h } from 'vue';",
		"import { usePlugin } from '@commera/admin';",
		`import Page from ${JSON.stringify(entry.file)};`,
		`import Detail from ${JSON.stringify(file)};`,
		'export default defineComponent({',
		'\tsetup() {',
		'\t\tconst { path } = usePlugin();',
		`\t\treturn () => (path.value ? h(Detail, { key: path.value, ${param}: path.value }) : h(Page));`,
		'\t},',
		'});',
	].join('\n');
}

function readHostFile(hostDir, name) {
	const path = join(hostDir, name);
	return existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null;
}

// Bound :class values are left to review: the dashboard's style law already forbids string-built class names.
function staticClasses(source) {
	const template = source.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? '';
	return [...template.matchAll(/\sclass="([^"]*)"/g)]
		.flatMap((match) => match[1].split(/\s+/))
		.filter(Boolean);
}

function stripPlainScript(compiler, code, id) {
	const { descriptor } = compiler.parse(code, { filename: id });
	const script = descriptor.script;
	if (!script) return null;
	const start = code.lastIndexOf('<script', script.loc.start.offset);
	const end = code.indexOf('</script>', script.loc.end.offset) + 9;
	return code.slice(0, start) + code.slice(end);
}

function guard({ hostDir, compiler, pluginFiles, pageEntries }) {
	const knownClasses = readHostFile(hostDir, 'classes.json');
	const sharedExports = readHostFile(hostDir, 'shared-exports.json');
	const knownClassSet = knownClasses ? new Set(knownClasses) : null;
	return {
		name: 'commera-plugin-guard',
		enforce: 'pre',
		buildStart() {
			if (!knownClassSet || !sharedExports) {
				this.warn(
					`no dashboard build at ${hostDir}; class and import checks skipped (build commera first)`,
				);
			}
		},
		resolveId(source) {
			if (source.endsWith(EMPTY_ENTRY_PATH)) return EMPTY_ENTRY;
			const pageEntry = source.split(PAGE_ENTRY_PATH)[1];
			if (pageEntries.has(pageEntry)) return `${PAGE_ENTRY}${pageEntry}`;
			const sharesRoot = SHARED_ROOTS.some((name) =>
				source.startsWith(`${name}/`),
			);
			if (sharesRoot && !SHARED.includes(source)) {
				this.error(
					`import '${source}' is not shared with app pages; use one of ${SHARED.join(
						', ',
					)}`,
				);
			}
		},
		load(id) {
			if (id === EMPTY_ENTRY) return 'export {};';
			if (id.startsWith(PAGE_ENTRY))
				return pageEntries.get(id.slice(PAGE_ENTRY.length));
		},
		transform(code, id) {
			if (id.includes('/node_modules/')) return;
			if (id.includes('?vue&type=style') || STYLESHEET.test(id)) {
				this.error(
					'app pages ship no CSS; use frappe-ui components and Tailwind classes',
				);
			}
			if (!id.endsWith('.vue')) return;
			if (knownClassSet) {
				const unknown = [...new Set(staticClasses(code))].filter(
					(name) => !knownClassSet.has(name),
				);
				if (unknown.length) {
					this.warn(
						`classes not in the dashboard's stylesheet yet: ${unknown.join(
							', ',
						)}; run bench build --app commera to add them`,
					);
				}
			}
			// The manifest is the only copy of the block, so dotted paths never reach the browser.
			if (pluginFiles.has(id)) {
				const stripped = stripPlainScript(compiler, code, id);
				if (stripped !== null) return { code: stripped, map: null };
			}
		},
		// The browser would otherwise refuse the module at runtime with "does not provide an export named …".
		generateBundle(_options, bundle) {
			const problems = [];
			for (const chunk of Object.values(bundle)) {
				if (chunk.type !== 'chunk') continue;
				for (const [specifier, names] of Object.entries(
					chunk.importedBindings,
				)) {
					const callsV1 = (name) =>
						specifier === 'frappe-ui' && FRAPPE_V1.has(name);
					for (const name of names.filter(callsV1)) {
						problems.push(
							`${chunk.fileName}: ${name} calls Frappe's v1 API, which this dashboard reads as null. Use useMethodRead / useMethodAction with a whitelisted method in your app's api.py.`,
						);
					}
					if (!sharedExports || !SHARED.includes(specifier)) continue;
					const available = sharedExports[specifier] ?? [];
					const missing = names.filter(
						(name) =>
							name !== '*' && !callsV1(name) && !available.includes(name),
					);
					if (missing.length) {
						problems.push(
							`${chunk.fileName}: '${specifier}' does not share ${missing.join(
								', ',
							)} with app pages${
								specifier === '@commera/admin'
									? ` (or ${hostDir} is from an older Commera: rebuild it with \`bench build --app commera\`)`
									: ''
							}`,
						);
					}
				}
			}
			if (problems.length) this.error(problems.join('\n'));
		},
	};
}

function manifestEntry(entry, hashes) {
	const fields = Object.fromEntries(
		GRAMMAR.places[entry.place].fields
			.filter((field) => field in entry.plugin)
			.map((field) => [field, entry.plugin[field]]),
	);
	const module = entry.entryName ? `${entry.entryName}.js` : null;
	return {
		place: entry.place,
		name: entry.name,
		module,
		hash: module ? hashes[module] : null,
		...fields,
	};
}

// The registry reads line 1, so the banner goes on after minification, which would strip or move a plain comment.
function finish({ app, entries, icon }) {
	return {
		name: 'commera-plugin-manifest',
		enforce: 'post',
		generateBundle(_options, bundle) {
			const hashes = {};
			for (const [fileName, chunk] of Object.entries(bundle)) {
				if (chunk.type !== 'chunk' || !chunk.isEntry) continue;
				if (chunk.facadeModuleId === EMPTY_ENTRY) {
					delete bundle[fileName];
					continue;
				}
				chunk.code = `${BANNER}\n${chunk.code}`;
				hashes[fileName] = createHash('sha1')
					.update(chunk.code)
					.digest('hex')
					.slice(0, 8);
			}
			if (icon)
				this.emitFile({ type: 'asset', fileName: ICON_FILE, source: icon });
			const manifest = {
				api_version: API_VERSION,
				kit_version: KIT_VERSION,
				app,
				...(icon ? { icon: ICON_FILE } : {}),
				entries: entries.map((entry) => manifestEntry(entry, hashes)),
			};
			this.emitFile({
				type: 'asset',
				fileName: 'manifest.json',
				source: `${JSON.stringify(manifest, null, '\t')}\n`,
			});
		},
	};
}

// Served as-is under /assets and shown with <img>, so it must also be safe to open directly.
function readAppIcon(sourceDir) {
	const path = join(sourceDir, ICON_FILE);
	if (!existsSync(path)) return { icon: null, errors: [] };
	const source = readFileSync(path, 'utf8');
	const outer = source
		.replace(/<\?xml[\s\S]*?\?>|<!--[\s\S]*?-->|<!DOCTYPE[^>]*>/gi, '')
		.trim();
	const problems = [];
	if (Buffer.byteLength(source) > ICON_LIMIT)
		problems.push(
			`is ${Math.ceil(
				Buffer.byteLength(source) / 1024,
			)} kB; keep it under 20 kB`,
		);
	if (!/^<svg[\s>]/i.test(outer) || !/<\/svg>$/i.test(outer))
		problems.push('must be a single <svg> element');
	if (/<script[\s>]/i.test(source)) problems.push('may not contain <script>');
	if (/\son[a-z]+\s*=/i.test(source))
		problems.push('may not use on* event attributes');
	if (/\s(?:xlink:)?href\s*=\s*(?:"(?!\s*#)|'(?!\s*#)|(?!["'#]))/i.test(source))
		problems.push('may only link to its own #ids');
	return {
		icon: problems.length ? null : source,
		errors: problems.map((problem) => `${ICON_FILE} ${problem}`),
	};
}

function requireFromApp(appRoot) {
	return createRequire(join(appRoot, 'package.json'));
}

// A `link:`ed kit resolves its own imports from apps/commera, where nothing is installed, so this resolves from the app.
// It imports the ESM entry because plugin-vue's CJS build requires Vite's deprecated CJS API.
async function importFromApp(appRoot, name) {
	let packageDir = dirname(requireFromApp(appRoot).resolve(name));
	while (!existsSync(join(packageDir, 'package.json')))
		packageDir = dirname(packageDir);
	const { exports } = JSON.parse(
		readFileSync(join(packageDir, 'package.json'), 'utf8'),
	);
	return import(pathToFileURL(join(packageDir, exports['.'].import)).href);
}

export default async function commeraPlugin({
	root = process.cwd(),
	app = basename(resolve(root)),
	hostDir,
} = {}) {
	// Vite reports module ids by real path, and the strip step matches files by id.
	const appRoot = realpathSync(resolve(root));
	const sourceDir = join(appRoot, 'commera');
	const resolvedHostDir =
		hostDir ?? resolve(appRoot, '../commera/commera/public/plugin-host');
	const { default: vue } = await importFromApp(appRoot, '@vitejs/plugin-vue');
	const compiler = requireFromApp(appRoot)('vue/compiler-sfc');
	const icons = readHostFile(resolvedHostDir, 'icons.json');
	const warnings = [];
	const discovered = discoverPlugins(sourceDir, {
		app,
		compiler,
		icons,
		warn: (message) => warnings.push(message),
	});
	const { entries } = discovered;
	const appIcon = readAppIcon(sourceDir);
	if (existsSync(join(sourceDir, 'icon.svg')))
		warnings.push(
			`commera/icon.svg is not used; rename it to commera/${ICON_FILE}`,
		);
	const errors = [...discovered.errors, ...appIcon.errors];
	if (errors.length) {
		throw new Error(
			`commera: ${errors.length} problem${
				errors.length === 1 ? '' : 's'
			} in ${app}/commera\n\n${errors
				.map((error) => `- ${error}`)
				.join('\n')}\n`,
		);
	}
	const pageEntries = new Map(
		entries
			.filter((entry) => entry.detail)
			.map((entry) => [entry.entryName, pageEntryCode(entry)]),
	);
	const moduleEntries = Object.fromEntries(
		entries
			.filter((entry) => entry.entryName)
			.map((entry) => [
				entry.entryName,
				pageEntries.has(entry.entryName)
					? `${PAGE_ENTRY_PATH}${entry.entryName}`
					: entry.file,
			]),
	);
	const pluginFiles = new Set(entries.map((entry) => entry.file));
	return [
		guard({ hostDir: resolvedHostDir, compiler, pluginFiles, pageEntries }),
		vue(),
		finish({ app, entries, icon: appIcon.icon }),
		{
			name: 'commera-plugin-build',
			buildStart() {
				if (!icons)
					this.warn(`no icons.json at ${resolvedHostDir}; icon check skipped`);
				for (const warning of warnings) this.warn(warning);
			},
			config: () => ({
				root: sourceDir,
				publicDir: false,
				define: { 'process.env.NODE_ENV': JSON.stringify('production') },
				build: {
					outDir: join(appRoot, app, 'public', 'commera'),
					emptyOutDir: true,
					target: 'es2022',
					minify: true,
					sourcemap: false,
					lib: {
						entry: Object.keys(moduleEntries).length
							? moduleEntries
							: { __empty: EMPTY_ENTRY_PATH },
						formats: ['es'],
						fileName: (_format, name) => `${name}.js`,
					},
					rollupOptions: {
						external: SHARED,
						output: { chunkFileNames: 'chunks/[name]-[hash].js' },
					},
				},
			}),
		},
	];
}
