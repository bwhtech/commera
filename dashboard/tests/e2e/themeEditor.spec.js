import assert from 'node:assert/strict'
import { describe } from 'node:test'
import { adminGet, adminPost, goto, uiTest, useSession, wait } from './harness.js'

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

  uiTest(session, 'Saving a theme setting re-renders the preview once with the new value', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')

    await goto(page, `/storefront/theme/${encodeURIComponent(theme.name)}/editor`)
    await page.waitForFunction(
      () => document.querySelector('iframe[data-preview-frame="visible"]')?.contentDocument?.querySelector('[data-commera-section]'),
      { timeout: 30000 },
    )
    const [settingsRow] = await page.$$('xpath/.//button[normalize-space()="Theme settings"]')
    await settingsRow.click()
    await page.waitForSelector('[id^="theme-"]', { visible: true })

    const field = await page.evaluate(() => {
      const preview = document.querySelector('iframe[data-preview-frame="visible"]').contentDocument.documentElement.outerHTML
      const inputs = [...document.querySelectorAll('input[id^="theme-"]')].filter((element) => element.type === 'text')
      const input =
        inputs.find((element) => element.id.endsWith('_url')) ??
        inputs.find((element) => element.value && preview.includes(element.value))
      return input && { id: input.id, fieldname: input.id.replace('theme-', ''), value: input.value }
    })
    if (!field) return t.skip('no theme setting of this theme shows in the preview')

    const changed = field.fieldname.endsWith('_url') ? `https://example.com/e2e-${Date.now()}` : `${field.value} E2E`
    const posts = []
    const countPost = (request) => {
      if (request.method() === 'POST' && request.url().includes('/theme_editor_preview')) posts.push(request.url())
    }
    page.on('request', countPost)

    try {
      await page.click(`#${field.id}`, { clickCount: 3 })
      await page.keyboard.type(changed)
      await page.keyboard.press('Tab')
      await page.waitForFunction(
        (text) =>
          document
            .querySelector('iframe[data-preview-frame="visible"]')
            .contentDocument.documentElement.outerHTML.includes(text),
        { timeout: 30000 },
        changed,
      )
      await wait(1000)
      assert.equal(posts.length, 1, 'one preview render for one saved setting')
    } finally {
      page.off('request', countPost)
      await adminPost(page, 'theme.save_theme_settings', { [field.fieldname]: field.value })
    }
  })
})
