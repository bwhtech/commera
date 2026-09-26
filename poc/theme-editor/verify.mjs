// Drives the prototype in Chromium: every interaction the editor promises,
// with screenshots in ./screenshots. Run `npm run build` first.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const PORT = 4190
const BASE = `http://localhost:${PORT}`
mkdirSync('screenshots', { recursive: true })
const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], { stdio: 'ignore' })
await new Promise((resolve) => setTimeout(resolve, 2500))

const results = []
const check = (name, ok, detail = '') => {
  results.push(ok)
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
const shot = (name) => page.screenshot({ path: `screenshots/${name}.png` })

try {
  await page.goto(BASE)
  await page.locator('[data-theme-card="summer_theme"]').waitFor()
  await shot('1-themes')
  await page.locator('[data-theme-card="summer_theme"]').getByRole('button', { name: 'Customize' }).click()

  const preview = page.frameLocator('[data-preview-frame]')
  await preview.locator('[data-section-id]').first().waitFor({ timeout: 10000 })
  check('editor opens with the home page rendered in the preview', true)
  await shot('2-editor-home')

  // Click a section in the preview: the tree and the settings panel follow.
  await preview.getByText('Made for long days').click()
  await page.locator('[data-settings-panel]').getByText('Slide').first().waitFor()
  check('clicking the preview selects that block and shows its settings', await page.locator('[data-settings-panel] h2').innerText() === 'Slide')

  // Edit a setting and watch the preview change.
  await page.locator('[data-field="heading"] input').fill('Hello from the editor')
  await preview.getByText('Hello from the editor').waitFor({ timeout: 5000 })
  check('editing a field updates the live preview', true)
  await shot('3-block-selected-and-edited')

  // Select a section from the tree.
  await page.locator('[data-tree-node]').filter({ hasText: 'Best picks' }).click()
  await page.locator('[data-field="columns"]').waitFor()
  check('clicking the tree selects the section and shows its settings', await page.locator('[data-settings-panel] h2').innerText() === 'Featured products')
  await shot('4-section-selected')

  // Drag a section above another in the tree; the preview follows the new order.
  const order = () => preview.locator('section.section').evaluateAll((sections) => sections.map((section) => section.dataset.label))
  const row = (text) => page.locator('[data-slot="row"]').filter({ has: page.locator('[data-tree-node]', { hasText: text }) })
  await row('Image with text').dragTo(row('Collection list'), { targetPosition: { x: 40, y: 3 } })
  await page.waitForTimeout(300)
  const after = await order()
  check('dragging in the tree reorders the page', after.indexOf('Image with text') < after.indexOf('Collection list'), after.slice(2, 6).join(' → '))
  await shot('4b-reordered')

  // Add a section from the Template group.
  await page.locator('[data-add-section="template"]').click()
  await page.getByRole('menuitem', { name: 'Newsletter' }).click()
  check('adding a section selects it', await page.locator('[data-settings-panel] h2').innerText() === 'Newsletter')

  // Product page: the main section carries a Printful app block.
  await page.locator('[data-template-select]').click()
  await page.getByRole('option', { name: 'Product' }).click()
  await preview.locator('.main-product').waitFor({ timeout: 5000 })
  await page.locator('[data-tree-node]').filter({ hasText: 'Size chart' }).click()
  check('app block from an app sits inside the theme section', (await page.locator('[data-settings-panel]').innerText()).includes('App block from Printful'))
  await shot('5-product-app-block')

  // Arabic + mobile.
  await page.getByRole('radio', { name: 'AR' }).click()
  await page.getByRole('radio', { name: 'Mobile' }).click()
  await page.locator('[data-template-select]').click()
  await page.getByRole('option', { name: 'Home page' }).click()
  await preview.locator('html[dir="rtl"]').waitFor({ timeout: 5000 })
  check('Arabic preview renders right-to-left', true)
  await page.waitForTimeout(400)
  await shot('6-arabic-mobile')

  // Theme settings.
  await page.getByRole('radio', { name: 'EN' }).click()
  await page.getByRole('radio', { name: 'Desktop' }).click()
  await page.locator('[data-tree-theme-settings]').click()
  await page.locator('[data-field="accent"] input[type="text"], [data-field="accent"] input:not([type="color"])').first().fill('#2563eb')
  await page.waitForTimeout(300)
  const accent = await preview.locator('html').evaluate((element) => element.style.getPropertyValue('--accent'))
  check('theme settings restyle the whole preview', accent === '#2563eb', accent)
  await shot('7-theme-settings')

  // Layout data and publish.
  await page.getByRole('button', { name: 'View layout data' }).click()
  await page.getByText('Theme Layout · summer_theme · index').waitFor()
  await page.waitForTimeout(500) // let the dialog finish fading in
  await shot('8-layout-json')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Publish' }).click()
  await page.getByText('Published to your storefront').waitFor()
  check('publish clears the unpublished badge', await page.getByText('Unpublished changes').count() === 0)
  check('no uncaught errors', errors.length === 0, errors.join(' | '))
} catch (error) {
  check('run completed', false, error.message.split('\n')[0])
  await shot('error')
} finally {
  await browser.close()
  server.kill()
}
console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`)
process.exit(results.every(Boolean) ? 0 : 1)
