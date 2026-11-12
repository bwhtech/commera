// Packs Twemoji's assets/svg folder into the one brotli JSON file that OG cards read.
// Usage: node scripts/build_twemoji_pack.mjs <twemoji>/assets/svg commera/og/twemoji/twemoji.json.br
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { constants, brotliCompressSync } from 'node:zlib';

const [svgDir, outFile] = process.argv.slice(2);
if (!svgDir || !outFile) {
	throw new Error('Usage: build_twemoji_pack.mjs <svg dir> <out file>');
}

const pack = {};
for (const file of readdirSync(svgDir).sort()) {
	if (file.endsWith('.svg')) {
		pack[file.slice(0, -4)] = readFileSync(join(svgDir, file), 'utf8').trim();
	}
}

const json = Buffer.from(JSON.stringify(pack));
const packed = brotliCompressSync(json, {
	params: {
		[constants.BROTLI_PARAM_QUALITY]: 11,
		[constants.BROTLI_PARAM_LGWIN]: 24,
		[constants.BROTLI_PARAM_SIZE_HINT]: json.length,
	},
});
writeFileSync(outFile, packed);
process.stdout.write(
	`${Object.keys(pack).length} graphics, ${json.length} bytes, ${
		packed.length
	} packed\n`,
);
