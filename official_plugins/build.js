import commeraPlugin from '@commera/plugin-kit/vite';
import { build } from 'vite';
import {
	OFFICIAL_DIR,
	PLUGIN_HOST_DIR,
	outDirOf,
	sourceDirOf,
} from '../dashboard/pluginApps.js';

const [app] = process.argv.slice(2);

await build({
	configFile: false,
	plugins: [
		await commeraPlugin({
			root: OFFICIAL_DIR,
			app,
			sourceDir: sourceDirOf(app),
			outDir: outDirOf(app),
			hostDir: PLUGIN_HOST_DIR,
		}),
	],
});
