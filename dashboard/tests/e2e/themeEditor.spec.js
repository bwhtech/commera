import assert from 'node:assert/strict'
import { describe } from 'node:test'
import { adminGet, goto, uiTest, useSession, wait } from './harness.js'

const SLOW_RENDER_MS = 1500

const REFUSAL = {
  status: 417,
  contentType: 'application/json',
  body: JSON.stringify({ errors: [{ type: 'ValidationError', message: 'A section setting has the wrong type.' }] }),
}

async function findLiveSectionsTheme(page) {
  const data = await adminGet(page, 'theme.get_editor_data')
  return data.themes.find((theme) => theme.live && theme.theme_type === 'Sections') ?? null
}

describe('theme editor', () => {
  const session = useSession()

  uiTest(session, 'Publish saves every part first, so a refused save publishes nothing', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')

    const calls = []
    await page.setRequestInterception(true)
    const intercept = (request) => {
      const method = request.url().match(/theme_layout\.(save_draft|publish)$/)?.[1]
      if (method) calls.push(method)
      if (method === 'save_draft') request.respond(REFUSAL)
      else request.continue()
    }
    page.on('request', intercept)

    try {
      await goto(page, `/storefront/theme/${encodeURIComponent(theme.name)}/editor`)
      await page.waitForSelector('[data-tree-node^="section:"]', { timeout: 30000 })
      await page.click('[data-tree-node^="section:"]')
      await page.waitForSelector('button[aria-label^="Hide "]', { visible: true })
      await page.click('button[aria-label^="Hide "]')
      await wait(500)

      const [publishButton] = await page.$$('xpath/.//button[normalize-space()="Publish"]')
      await publishButton.click()
      await wait(2500)

      assert.deepEqual(calls, ['save_draft'])
      const body = await page.evaluate(() => document.body.innerText)
      assert.ok(body.includes('Unpublished changes'), 'the edit is kept and still unpublished')
      await page.click('button[aria-label^="Show "]')
      await wait(500)
    } finally {
      page.off('request', intercept)
      await page.setRequestInterception(false)
    }
  })

  uiTest(session, 'A slow preview render dims the preview until the new page swaps in', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')

    await page.setRequestInterception(true)
    const intercept = (request) => {
      if (request.method() === 'POST' && request.url().includes('/theme_editor_preview')) {
        setTimeout(() => request.continue(), SLOW_RENDER_MS)
      } else request.continue()
    }
    page.on('request', intercept)

    try {
      await goto(page, `/storefront/theme/${encodeURIComponent(theme.name)}/editor`)
      await page.waitForSelector('[data-tree-node^="section:"]', { timeout: 30000 })
      await page.waitForSelector('[data-preview-rendering]', { hidden: true, timeout: 30000 })
      await page.click('[data-tree-node^="section:"]')
      await page.waitForSelector('button[aria-label^="Hide "]', { visible: true })
      await page.click('button[aria-label^="Hide "]')

      await page.waitForSelector('[data-preview-rendering]', { visible: true, timeout: SLOW_RENDER_MS })
      const blocked = await page.evaluate(() => {
        const frame = document.querySelector('iframe[data-preview-frame="visible"]').getBoundingClientRect()
        const top = document.elementFromPoint(frame.left + frame.width / 2, frame.top + frame.height / 2)
        return Boolean(top?.closest('[data-preview-rendering]'))
      })
      assert.ok(blocked, 'the overlay sits over the preview and takes its clicks')

      await page.waitForSelector('[data-preview-rendering]', { hidden: true, timeout: 30000 })
      const settled = await page.evaluate(() =>
        [...document.querySelector('iframe[data-preview-frame="visible"]').contentDocument.querySelectorAll('.wow')].every(
          (element) => getComputedStyle(element).visibility === 'visible' && getComputedStyle(element).animationName === 'none',
        ),
      )
      assert.ok(settled, 'the re-rendered page lands without entrance animations')

      await page.click('button[aria-label^="Show "]')
      await page.waitForSelector('[data-preview-rendering]', { visible: true, timeout: SLOW_RENDER_MS })
      await page.waitForSelector('[data-preview-rendering]', { hidden: true, timeout: 30000 })
    } finally {
      page.off('request', intercept)
      await page.setRequestInterception(false)
    }
  })
})
