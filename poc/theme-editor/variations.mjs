// Screenshots of the three page-management variations (src/variations).
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const PORT = 4191
mkdirSync('screenshots/variations', { recursive: true })
const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], { stdio: 'ignore' })
await new Promise((resolve) => setTimeout(resolve, 2500))
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
const shot = async (name) => {
  await page.waitForTimeout(400)
  await page.screenshot({ path: `screenshots/variations/${name}.png` })
}
const go = async (path) => {
  await page.goto(`http://localhost:${PORT}${path}`)
  await page.waitForLoadState('networkidle')
}

try {
  await go('/variations')
  await shot('0-index')

  await go('/variations/a')
  await shot('a1-theme')
  await page.locator('[data-nav="pages"]').click()
  await shot('a2-pages')
  await page.locator('[data-new-page-button]').click()
  await page.locator('[data-page-title]').fill('Winter sale')
  await shot('a3-new-page')

  await go('/variations/b')
  await shot('b1-pages')
  await page.locator('[data-nav="theme"]').click()
  await shot('b2-look-and-feel')

  await go('/variations/c')
  await shot('c1-pages')
  await page.locator('[data-new-page-button]').click()
  await shot('c2-new-page-kind')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
  await page.locator('[data-row="About us"]').getByRole('button', { name: 'Edit' }).click()
  await page.locator('[data-text-editor]').waitFor()
  await shot('c3-text-page-editor')
  console.log(errors.length ? `errors: ${errors.join(' | ')}` : 'ok, no page errors')
} finally {
  await browser.close()
  server.kill()
}
