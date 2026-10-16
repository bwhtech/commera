// Walks the /storefront hierarchy (src/storefront): themes as the core,
// "Create with Frappe Builder" as a theme kind, and rich text content pages.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const PORT = 4192
mkdirSync('screenshots/storefront', { recursive: true })
const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], { stdio: 'ignore' })
await new Promise((resolve) => setTimeout(resolve, 2500))
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('popup', (popup) => popup.close())
const shot = async (name, options = {}) => {
  await page.waitForTimeout(400)
  await page.screenshot({ path: `screenshots/storefront/${name}.png`, ...options })
}
const go = async (path) => {
  await page.goto(`http://localhost:${PORT}${path}`)
  await page.waitForLoadState('networkidle')
}

try {
  await go('/storefront')
  await page.locator('[data-live-theme]').waitFor()
  await shot('1-themes')

  await page.locator('[data-add-theme]').click()
  await shot('2-add-theme-menu')
  await page.getByText('Create with Frappe Builder').click()
  await page.locator('[data-create-theme]').waitFor()
  await page.locator('[data-theme-name] input, input[data-theme-name]').first().fill('Winter 2026')
  await shot('3-create-builder-theme')
  await page.locator('[data-create-theme-submit]').click()
  await page.locator('[data-theme-page="home"]').waitFor()
  await shot('4-builder-theme-empty', { fullPage: true })

  for (const key of ['chrome', 'home', 'product']) {
    await page.locator(`[data-theme-page="${key}"] button`).last().click()
  }
  await shot('5-builder-theme-partly-designed', { fullPage: true })
  for (const key of ['collection', 'page']) {
    await page.locator(`[data-theme-page="${key}"] button`).last().click()
  }
  await page.locator('[data-publish-theme]:not([disabled])').click()
  await page.waitForTimeout(400)
  const dialogButton = page.getByRole('dialog').getByRole('button', { name: 'Publish' })
  if (await dialogButton.count()) await dialogButton.click()
  // Publishing routes back to Themes in-app (a reload would reset the prototype's state).
  await page.locator('[data-live-theme]', { hasText: 'Winter 2026' }).waitFor()
  await page.waitForTimeout(3500) // let the toast clear
  await shot('6-themes-after-publish')

  await go('/storefront/pages')
  await page.locator('[data-content-page]').first().waitFor()
  await shot('7-pages')
  await page.locator('[data-content-page="about-us"]').click()
  await page.locator('[data-page-editor]').waitFor()
  await shot('8-page-editor', { fullPage: true })
  await page.getByText('العربية', { exact: true }).click()
  await shot('9-page-editor-arabic', { fullPage: true })

  console.log(errors.length ? `errors: ${errors.join(' | ')}` : 'ok, no page errors')
} finally {
  await browser.close()
  server.kill()
}
