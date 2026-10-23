// Why extensions share the host's frappe-ui instead of bundling their own:
// builds the Printful app both ways and checks whether a toast imported
// straight from 'frappe-ui' ever appears. Restores the normal build afterwards.
import { execSync, spawn } from 'node:child_process'
import { chromium } from 'playwright-core'

const build = (config) => execSync(`npx vite build --config commera/${config}`, { cwd: 'apps/printful', stdio: 'ignore' })
const server = spawn('node', ['server.mjs'], { env: { ...process.env, PORT: '4184' } })
await new Promise((resolve) => setTimeout(resolve, 500))
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

for (const [label, config] of [['bundled frappe-ui', 'vite.bundled.config.js'], ['shared frappe-ui', 'vite.config.js']]) {
  build(config)
  const page = await browser.newPage()
  await page.goto('http://localhost:4184/apps/printful/printful')
  await page.getByRole('button', { name: 'Direct toast' }).click()
  const shown = await page.getByText('Toast via frappe-ui import').waitFor({ timeout: 4000 }).then(() => true, () => false)
  console.log(`${label.padEnd(18)} toast imported from 'frappe-ui' ${shown ? 'shows' : 'NEVER shows'}`)
  await page.close()
}

await browser.close()
server.kill()
