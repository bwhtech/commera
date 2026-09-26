// What does sharing the runtime cost the host? Builds the host a second time
// without the three runtime entries and compares total JS. Run after `npm run build`.
import { build } from 'vite'
import { readdirSync, readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { fileURLToPath } from 'node:url'

const hostDir = fileURLToPath(new URL('./host/', import.meta.url))
process.chdir(hostDir)
const { default: config } = await import('./host/vite.config.js')

await build({
  ...config,
  configFile: false,
  logLevel: 'silent',
  plugins: config.plugins.flat().filter((plugin) => plugin?.name !== 'commera-shared-runtime'),
  build: {
    ...config.build,
    outDir: '../.baseline-dist',
    rollupOptions: { input: { index: `${hostDir}index.html` } },
  },
})

function totals(dir) {
  const files = readdirSync(`${dir}/assets`).filter((file) => file.endsWith('.js'))
  const bytes = files.map((file) => readFileSync(`${dir}/assets/${file}`))
  const kb = (n) => `${(n / 1024).toFixed(1)} kB`
  return `${kb(bytes.reduce((sum, b) => sum + b.length, 0))} (gzip ${kb(bytes.reduce((sum, b) => sum + gzipSync(b).length, 0))}) in ${files.length} files`
}

console.log(`host without shared runtime: ${totals(`${hostDir}../.baseline-dist`)}`)
console.log(`host with shared runtime:    ${totals(`${hostDir}dist`)}`)
