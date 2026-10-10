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
const pickPage = async (name) => {
  await page.locator('[data-page-picker]').click()
  await page.getByRole('menuitem', { name, exact: true }).click()
}
// Builder opens in a new tab; the check is the URL Commera hands it.
const builderTab = async (action) => {
  const [popup] = await Promise.all([page.context().waitForEvent('page'), action()])
  const url = new URL(popup.url())
  await popup.close()
  return url.pathname + url.search
}

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
  await pickPage('Product')
  await preview.locator('.main-product').waitFor({ timeout: 5000 })
  await page.locator('[data-tree-node]').filter({ hasText: 'Size chart' }).click()
  check('app block from an app sits inside the theme section', (await page.locator('[data-settings-panel]').innerText()).includes('App block from Printful'))
  await shot('5-product-app-block')

  // Arabic + mobile.
  await page.getByRole('radio', { name: 'AR' }).click()
  await page.getByRole('radio', { name: 'Mobile' }).click()
  await pickPage('Home page')
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

  // Builder: a theme section that embeds a Builder component, edited in Builder.
  await page.locator('[data-add-section="template"]').click()
  await page.getByRole('menuitem', { name: 'Builder component' }).click()
  await preview.locator('.countdown').first().waitFor({ timeout: 5000 })
  await page.waitForTimeout(900) // the preview smooth-scrolls to the new section
  await shot('10-builder-component-section')
  const componentUrl = await builderTab(() => page.locator('[data-edit-component]').click())
  check('"Edit in Builder" on a component section opens that component', componentUrl === '/builder/component/countdown-banner', componentUrl)

  // Builder: a Builder page in the page picker, shown inside the store layout.
  await pickPage('Summer sale')
  await preview.locator('[data-builder-page]').waitFor({ timeout: 5000 })
  check('a Builder page previews inside the theme header and footer', await preview.locator('.site-header').count() === 1)
  await page.waitForTimeout(300)
  await shot('9-builder-page-in-editor')
  const pageUrl = await builderTab(() => page.locator('[data-edit-in-builder]').click())
  check('"Edit in Builder" on a Builder page opens it in Builder', pageUrl === '/builder/page/summer-sale', pageUrl)
  await page.locator('[data-builder-page-panel]').getByRole('switch').click()
  await page.waitForTimeout(300)
  check("turning off the store layout drops the theme's header", await preview.locator('.site-header').count() === 0)
  await page.locator('[data-builder-page-panel]').getByRole('switch').click()
  await pickPage('Home page')

  // Layout data and publish.
  await page.getByRole('button', { name: 'View layout data' }).click()
  await page.getByText('Theme Layout · summer_theme · index').waitFor()
  await page.waitForTimeout(500) // let the dialog finish fading in
  await shot('8-layout-json')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Publish' }).click()
  await page.getByText('Published to your storefront').waitFor()
  check('publish clears the unpublished badge', await page.getByText('Unpublished changes').count() === 0)
  // Pages list: theme pages and Builder pages together; a new page starts in Builder.
  await page.goto(`${BASE}/pages`)
  await page.locator('[data-builder-row="summer-sale"]').waitFor()
  await shot('11-pages-list')
  await page.locator('[data-new-page]').click()
  await page.locator('[data-new-page-title]').fill('Winter drop')
  await page.locator('[data-new-page-prompt] textarea, textarea[data-new-page-prompt]').first().fill('A landing page for our winter hoodie drop with a countdown and the Hoodies collection.')
  await page.waitForTimeout(300)
  await shot('12-new-page-dialog')
  const newUrl = await builderTab(() => page.locator('[data-create-in-builder]').click())
  check('"Create in Builder" hands the prompt and layout to Builder', newUrl.startsWith('/builder/page/new?prompt=') && newUrl.includes('layout=commera-theme'), newUrl.slice(0, 60))
  await page.locator('[data-builder-row="winter-drop"]').waitFor({ timeout: 5000 })
  check('the new page is listed as a draft', (await page.locator('[data-builder-row="winter-drop"]').innerText()).includes('Draft'))

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
