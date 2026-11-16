import fs from 'node:fs';
import vue from '@vitejs/plugin-vue';
import tailwindcss from 'tailwindcss';
import { defineConfig } from 'vite';

// The editor serves these modules through its import map, so the plugin shares its Vue, stores and frappe-ui.
const SHARED_MODULES = ['builder', 'vue', 'pinia', 'frappe-ui'];
const isShared = (id) =>
	SHARED_MODULES.includes(id) || id.startsWith('builder/internal/');

/**
 * The package layout Builder loads: the manifest and the icon next to `main.js`, and an entry that links
 * the stylesheet. Mirrors the build of `frappe-builder-plugin-sdk/vite`.
 */
function builderPackage() {
	return {
		name: 'commera-builder-package',
		generateBundle: {
			// Vite's CSS plugin adds the stylesheet in this same hook
			order: 'post',
			handler(_options, bundle) {
				const source = fs.readFileSync('manifest.json', 'utf8');
				const manifest = JSON.parse(source);
				this.emitFile({ type: 'asset', fileName: 'manifest.json', source });
				this.emitFile({
					type: 'asset',
					fileName: manifest.icon,
					source: fs.readFileSync(`src/${manifest.icon}`),
				});

				const files = Object.values(bundle);
				const sheet = files.find((file) => file.fileName.endsWith('.css'));
				const entry = files.find(
					(file) => file.type === 'chunk' && file.isEntry,
				);
				// the editor's styles load after this link, so they win a tie with the plugin's
				entry.code = `(() => { const link = document.createElement("link"); link.rel = "stylesheet"; link.href = new URL(${JSON.stringify(sheet.fileName)}, import.meta.url).href; document.head.prepend(link); })();\n${entry.code}`;
			},
		},
	};
}

export default defineConfig({
	// a chunk or an asset resolves against the module that names it, so the build works under any URL
	base: './',
	css: {
		postcss: { plugins: [tailwindcss({ config: './tailwind.config.js' })] },
	},
	plugins: [vue(), builderPackage()],
	build: {
		outDir: '../public/builder_plugins/builder_plugin',
		emptyOutDir: true,
		target: 'es2020',
		cssCodeSplit: false,
		rollupOptions: {
			input: 'src/main.js',
			preserveEntrySignatures: 'strict',
			external: isShared,
			output: {
				entryFileNames: 'main.js',
				chunkFileNames: 'chunks/[name]-[hash].js',
				assetFileNames: 'assets/[name]-[hash][extname]',
			},
		},
	},
});
