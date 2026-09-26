// JS a browser actually downloads per page, with the shared runtime on.
import { spawn } from 'node:child_process'
import { gzipSync } from 'node:zlib'
import { chromium } from 'playwright-core'

const PORT = 4181
const server = spawn('node', ['server.mjs'], { env: { ...process.env, PORT: String(PORT) } })
await new Promise((resolve) => setTimeout(resolve, 500))
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

for (const path of ['/', '/apps/printful/printful', '/orders/SO-1001']) {
  const page = await browser.newPage()
  let raw = 0
  let gzip = 0
  page.on('response', async (response) => {
    if (!response.url().endsWith('.js') && !response.url().includes('.js?v=')) return
    const body = await response.body().catch(() => Buffer.alloc(0))
    raw += body.length
    gzip += gzipSync(body).length
  })
  await page.goto(`http://localhost:${PORT}${path}`, { waitUntil: 'networkidle' })
  console.log(`${path.padEnd(26)} ${(raw / 1024).toFixed(1)} kB JS (gzip ${(gzip / 1024).toFixed(1)} kB)`)
  await page.close()
}
await browser.close()
server.kill()
