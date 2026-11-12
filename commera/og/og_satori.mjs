// Renders an OG card (HTML -> SVG via satori -> PNG via resvg) for the Python
// og_image_render controller. Payload comes in on stdin (not argv) because the
// HTML is large and contains shell-unsafe characters; the raw PNG goes to stdout.
import { readFileSync } from 'node:fs';
import { Resvg } from '@resvg/resvg-js';
import satori from 'satori';
import { html } from 'satori-html';
import { prepareTree } from './og_bidi.mjs';
import {
	graphemeImages,
	loadAdditionalAsset,
	withRenderableText,
} from './og_glyphs.mjs';

async function readStdin() {
	const chunks = [];
	for await (const chunk of process.stdin) {
		chunks.push(chunk);
	}
	return Buffer.concat(chunks).toString('utf8');
}

async function main() {
	const payload = JSON.parse(await readStdin());

	const fonts = (payload.fonts || []).map((font) => ({
		name: font.name,
		data: readFileSync(font.path),
		weight: font.weight,
		style: font.style,
	}));

	const markup = prepareTree(
		withRenderableText(html(payload.html)),
		payload.direction,
	);
	const svg = await satori(markup, {
		width: payload.width,
		height: payload.height,
		fonts,
		graphemeImages: graphemeImages(markup),
		loadAdditionalAsset,
	});

	const png = new Resvg(svg, {
		fitTo: { mode: 'width', value: payload.width },
	})
		.render()
		.asPng();

	process.stdout.write(png);
}

main().catch((error) => {
	process.stderr.write(String(error?.stack ? error.stack : error));
	process.exit(1);
});
