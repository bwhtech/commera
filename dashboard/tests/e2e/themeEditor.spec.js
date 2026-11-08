import assert from 'node:assert/strict'
import { describe } from 'node:test'
import { adminGet, adminPost, goto, uiTest, useSession, wait } from './harness.js'

const SLOW_RENDER_MS = 1500
const WORKSPACE_STORAGE = ['commera:theme-editor:zoom', 'commera-theme-editor-panels']

const REFUSAL = {
  status: 417,
  contentType: 'application/json',
  body: JSON.stringify({ errors: [{ type: 'ValidationError', message: 'A section setting has the wrong type.' }] }),
}

async function findLiveSectionsTheme(page) {
  const data = await adminGet(page, 'theme.get_editor_data')
  return data.themes.find((theme) => theme.live && theme.theme_type === 'Sections') ?? null
}

async function openEditor(page, theme, { clearWorkspace = false } = {}) {
  page.removeAllListeners('dialog')
  page.on('dialog', (dialog) => dialog.accept())
  await goto(page, `/storefront/theme/${encodeURIComponent(theme.name)}/editor`)
  if (clearWorkspace) {
    await page.evaluate((keys) => {
      for (const key of Object.keys(localStorage)) {
        if (keys.some((part) => key.includes(part))) localStorage.removeItem(key)
      }
    }, WORKSPACE_STORAGE)
    await page.reload({ waitUntil: 'networkidle2' })
  }
  await page.waitForSelector('[data-tree-node^="section:"]', { timeout: 30000 })
  await page.waitForSelector('[data-preview-frame="visible"]', { timeout: 30000 })
}

const panelWidth = (page, name) =>
  page.$eval(`[data-editor-panel="${name}"]`, (element) => Math.round(element.getBoundingClientRect().width))

const previewScale = (page) => page.$eval('[data-preview-canvas]', (element) => Number(element.dataset.previewScale))

const box = async (page, selector) => (await page.$(selector)).boundingBox()

async function setZoom(page, value) {
  await page.click(`[aria-label="Preview zoom"] [data-value="${value}"]`)
  await wait(500)
}

async function wheelOver(page, device) {
  const frame = await box(page, `[data-preview-device="${device}"] iframe[data-preview-frame="visible"]`)
  await page.mouse.move(frame.x + frame.width / 2, frame.y + frame.height / 2)
  await page.mouse.wheel({ deltaY: 600 })
  await wait(600)
}

async function dragBy(page, selector, deltaX, deltaY = 0) {
  const box = await (await page.$(selector)).boundingBox()
  const startX = box.x + box.width / 2
  const startY = box.y + Math.min(box.height / 2, 300)
  await page.mouse.move(startX, startY)
  await wait(100)
  await page.mouse.down()
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 8 })
  await page.mouse.up()
  await wait(300)
}

async function openThemeSettings(page) {
  await page.click('[data-theme-settings-toggle]')
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[data-theme-layout-editor] > aside')
      const column = document.querySelector('[data-editor-panel="settings"]')
      return panel && Math.round(panel.getBoundingClientRect().width) === Math.round(column.getBoundingClientRect().width)
    },
    { timeout: 5000 },
  )
}

async function pickPreviewOption(page, label) {
  await page.click('[data-zoom-controls] button[aria-label="More preview options"]')
  await page.waitForSelector('[data-preview-options]', { visible: true })
  const directions = { 'Left to right': 'en', 'Right to left': 'ar' }
  if (directions[label]) await page.click(`[data-preview-options] [aria-label="Text direction"] [data-value="${directions[label]}"]`)
  else await page.click(`[data-preview-options] [aria-label="${label}"]`)
  await page.keyboard.press('Escape')
  await wait(400)
}

async function clickButton(page, label) {
  await page.click(`button[aria-label="${label}"]`)
  await wait(400)
}

function outlineShown(frame) {
  return frame.evaluate(() => document.querySelectorAll('[data-commera-outline]').length > 0)
}

async function visibleFrame(page, device) {
  const handle = await page.$(`[data-preview-device="${device}"] iframe[data-preview-frame="visible"]`)
  return handle.contentFrame()
}

describe('theme editor', () => {
  const session = useSession()

  uiTest(session, 'The top bar keeps Save and Publish on and shows Discard only with something to discard', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme)
    const shown = () =>
      page.$$eval('header button', (buttons) =>
        Object.fromEntries(
          buttons
            .filter((button) => ['Discard', 'Save', 'Publish'].includes(button.textContent.trim()))
            .map((button) => [button.textContent.trim(), !button.disabled]),
        ),
      )
    const toastAfter = async (label, message) => {
      const [button] = await page.$$(`xpath/.//header//button[normalize-space()="${label}"]`)
      await button.click()
      await page.waitForFunction(
        (message) => [...document.querySelectorAll('[data-sonner-toast]')].some((node) => node.textContent.includes(message)),
        { timeout: 5000 },
        message,
      )
    }

    const pending = (await page.$eval('header', (element) => element.innerText)).includes('Unpublished changes')
    if (pending) {
      assert.deepEqual(await shown(), { Discard: true, Save: true, Publish: true })
    } else {
      assert.ok((await page.$eval('header', (element) => element.innerText)).includes('Published'))
      assert.deepEqual(await shown(), { Save: true, Publish: true }, 'nothing to discard, so no Discard')
      await toastAfter('Publish', 'Already published')
    }
    await toastAfter('Save', 'Nothing to save')

    await page.click('[data-tree-node^="section:"]')
    await page.waitForSelector('[data-settings-panel] button[aria-label="Hide section"]', { visible: true })
    await page.click('[data-settings-panel] button[aria-label="Hide section"]')
    await wait(300)
    assert.deepEqual(await shown(), { Discard: true, Save: true, Publish: true })

    await page.click('[data-settings-panel] button[aria-label="Show section"]')
    await wait(300)
    assert.equal('Discard' in (await shown()), pending, 'undoing the edit leaves only what was there before')
  })

  uiTest(session, 'A refused save keeps the edit unsaved and publishes nothing', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')

    const calls = []
    await page.setRequestInterception(true)
    const intercept = (request) => {
      const method = request.url().match(/theme_layout\.(save_draft|publish)$/)?.[1]
      if (method) calls.push(method)
      if (method === 'save_draft') setTimeout(() => request.respond(REFUSAL), SLOW_RENDER_MS)
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

      const header = () => page.$eval('header', (element) => element.innerText)
      const [saveButton] = await page.$$('xpath/.//header//button[normalize-space()="Save"]')
      await saveButton.click()
      await wait(300)
      const states = await page.$$eval('header button', (buttons) =>
        Object.fromEntries(
          buttons
            .filter((button) => ['Discard', 'Save', 'Publish'].includes(button.textContent.trim()))
            .map((button) => [button.textContent.trim(), button.getAttribute('aria-busy') ? 'loading' : button.disabled ? 'disabled' : 'enabled']),
        ),
      )
      assert.deepEqual(states, { Discard: 'disabled', Save: 'loading', Publish: 'disabled' })
      await wait(2500)

      assert.deepEqual(calls, ['save_draft'])
      assert.ok((await header()).includes('Unpublished changes'), 'the edit is kept and still unpublished')
      const saveOn = await page.$eval('xpath/.//header//button[normalize-space()="Save"]', (button) => !button.disabled)
      assert.ok(saveOn, 'Save stays on so the edit can be retried')
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

  uiTest(session, 'A failed preview render clears the overlay and keeps the last page usable', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme)
    await page.waitForSelector('[data-preview-rendering]', { hidden: true, timeout: 30000 })

    await page.setRequestInterception(true)
    const intercept = (request) => {
      if (request.method() === 'POST' && request.url().includes('/theme_editor_preview')) {
        const badGateway = { status: 502, contentType: 'text/html', body: '<h1>502 Bad Gateway</h1>' }
        setTimeout(() => request.respond(badGateway), SLOW_RENDER_MS)
      } else request.continue()
    }
    page.on('request', intercept)

    try {
      await page.click('[data-tree-node^="section:"]')
      await page.waitForSelector('button[aria-label^="Hide "]', { visible: true })
      await page.click('button[aria-label^="Hide "]')
      await page.waitForSelector('[data-preview-rendering]', { visible: true, timeout: SLOW_RENDER_MS })
      await page.waitForSelector('[data-preview-rendering]', { hidden: true, timeout: 5000 })
      const body = await page.evaluate(() => document.body.innerText)
      assert.ok(body.includes('The preview could not be updated'), 'the merchant is told the preview did not update')
      const shown = await (await visibleFrame(page, 'desktop')).evaluate(() => document.body.innerText)
      assert.ok(!shown.includes('502 Bad Gateway'), 'the last good page stays in the preview')
    } finally {
      page.off('request', intercept)
      await page.setRequestInterception(false)
      await page.click('button[aria-label^="Show "]')
      await wait(500)
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
    await openThemeSettings(page)

    const field = await page.evaluate(() => {
      const preview = document.querySelector('iframe[data-preview-frame="visible"]').contentDocument.documentElement.outerHTML
      const inputs = [...document.querySelectorAll('input[id^="theme-"]')].filter(
        (element) => element.type === 'text' && !element.readOnly && !element.disabled,
      )
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
      await page.click('[data-theme-settings-panel] > :last-child button')
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
      await adminPost(page, 'theme.save_theme_settings', { theme: theme.name, [field.fieldname]: field.value })
    }
  })

  uiTest(session, 'A new section made only of blocks says how to add its first block', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    const editorData = await adminGet(page, 'theme_layout.get_editor', { theme: theme.name, page: 'index' })
    const schema = editorData.section_schemas.find(
      (candidate) =>
        (candidate.groups ?? ['pages']).includes('pages') &&
        !candidate.settings?.length &&
        Object.keys(candidate.blocks ?? {}).length,
    )
    if (!schema) return t.skip('this theme has no home page section made only of blocks')
    await openEditor(page, theme)

    const [addButton] = await page.$$(
      'xpath/.//button[normalize-space()="Add section" or @aria-label="Add section to Home page"]',
    )
    await addButton.click()
    await page.click(`[data-section-type="${schema.type}"]`)
    await page.waitForSelector('[data-settings-panel]', { visible: true })
    try {
      const panel = await page.$eval('[data-settings-panel]', (element) => element.innerText)
      const blockName = Object.values(schema.blocks)[0].name
      assert.ok(panel.includes(`Add a ${blockName}`), `the panel says "${panel.replace(/\s+/g, ' ')}"`)
      assert.ok(!panel.includes('Drag it in the list'), 'it does not point the merchant at dragging')
    } finally {
      await page.click('[data-settings-panel] button[aria-label="Remove section"]')
      await wait(500)
    }
  })

  uiTest(session, 'A theme that is not active is never called live', async (t) => {
    const { page } = session
    const data = await adminGet(page, 'theme.get_editor_data')
    const theme = data.themes.find((candidate) => !candidate.live && candidate.theme_type === 'Sections')
    if (!theme) return t.skip('every Sections theme is live')
    await openEditor(page, theme)
    const header = await page.$eval('header', (element) => element.innerText)
    assert.ok(!/\bLive\b/.test(header), `the header says "${header.replace(/\s+/g, ' ')}"`)
    assert.ok(header.includes('Not live'), 'the badge says the theme is not live')
  })

  uiTest(session, 'A refused theme settings save keeps what was typed', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme)
    await openThemeSettings(page)
    const field = await page.evaluate(() => {
      const input = [...document.querySelectorAll('input[id^="theme-"]')].find(
        (element) => element.type === 'text' && !element.readOnly && !element.disabled,
      )
      return input && { id: input.id, value: input.value }
    })
    if (!field) return t.skip('this theme has no text theme setting')

    await page.setRequestInterception(true)
    const intercept = (request) => {
      if (request.url().includes('theme.save_theme_settings')) request.respond(REFUSAL)
      else request.continue()
    }
    page.on('request', intercept)

    try {
      const saveDisabled = () => page.$eval('[data-theme-settings-panel] > :last-child button', (button) => button.disabled)
      assert.ok(await saveDisabled(), 'Save is off until something changes')
      await page.click(`#${field.id}`)
      await page.keyboard.type(' refused')
      assert.ok(!(await saveDisabled()), 'Save turns on after a change')
      await page.click('[data-theme-settings-panel] > :last-child button')
      await wait(1500)
      assert.equal(await page.$eval(`#${field.id}`, (element) => element.value), `${field.value} refused`)
      assert.ok(!(await saveDisabled()), 'Save stays on so the change can be retried')
    } finally {
      page.off('request', intercept)
      await page.setRequestInterception(false)
    }
  })

  uiTest(session, 'The tree resizes, never folds away, and keeps its size after a reload', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme, { clearWorkspace: true })

    const treeWidth = await panelWidth(page, 'tree')
    await dragBy(page, '[data-editor-handle="tree"]', 80)
    const widened = await panelWidth(page, 'tree')
    assert.ok(Math.abs(widened - treeWidth - 80) <= 4, `tree ${treeWidth} -> ${widened}`)

    await dragBy(page, '[data-editor-handle="tree"]', -600)
    assert.ok(Math.abs((await panelWidth(page, 'tree')) - 220) <= 2, 'a hard drag stops at the minimum, it never folds the tree away')
    await dragBy(page, '[data-editor-handle="tree"]', widened - 220)

    assert.equal(await panelWidth(page, 'settings'), 0, 'with nothing selected there is no settings column')
    await openThemeSettings(page)
    await clickButton(page, 'Close theme settings')
    assert.equal(await page.$('[data-theme-settings-panel]'), null, 'theme settings close at once')
    assert.equal(await panelWidth(page, 'settings'), 0, 'closing with nothing selected folds the column away')
    await page.click('[data-tree-node^="section:"]')
    const settingsWidth = await panelWidth(page, 'settings')
    assert.ok(settingsWidth > 0, 'selecting a section opens its settings')
    await openThemeSettings(page)
    await clickButton(page, 'Close theme settings')
    assert.ok(await page.$('[data-settings-panel]'), 'closing goes back to the section that was selected')

    await page.reload({ waitUntil: 'networkidle2' })
    await page.waitForSelector('[data-tree-node^="section:"]', { timeout: 30000 })
    assert.equal(await panelWidth(page, 'tree'), widened)
    assert.equal(await panelWidth(page, 'settings'), 0, 'a reload starts with nothing selected')
  })

  uiTest(session, 'The preview fits the canvas, scrolls its own page and maximises', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme, { clearWorkspace: true })

    const canvas = await box(page, '[data-preview-canvas]')
    const fit = await previewScale(page)
    const frameBefore = await box(page, '[data-preview-device="desktop"] iframe[data-preview-frame="visible"]')
    assert.ok(fit > 0.1 && fit <= 1, `fit is ${fit}`)
    assert.ok(frameBefore.x >= canvas.x && frameBefore.x + frameBefore.width <= canvas.x + canvas.width + 1, 'fit keeps the desktop frame inside the canvas')
    assert.ok(frameBefore.y + frameBefore.height <= canvas.y + canvas.height, 'the frame ends inside the canvas')

    const desktop = await visibleFrame(page, 'desktop')
    const scrolledBefore = await desktop.evaluate(() => window.scrollY)
    await wheelOver(page, 'desktop')
    assert.ok((await desktop.evaluate(() => window.scrollY)) > scrolledBefore, 'the wheel scrolls the storefront page')
    assert.deepEqual(await box(page, '[data-preview-device="desktop"] iframe[data-preview-frame="visible"]'), frameBefore, 'the frame does not move')

    await setZoom(page, '1')
    assert.equal(await previewScale(page), 1)
    await setZoom(page, '0.75')
    assert.equal(await previewScale(page), 0.75)
    await setZoom(page, 'fit')
    assert.equal(await previewScale(page), fit)

    const treeWidth = await panelWidth(page, 'tree')
    await clickButton(page, 'Maximise preview')
    await wait(400)
    assert.equal(await panelWidth(page, 'tree'), 0)
    assert.equal(await panelWidth(page, 'settings'), 0)
    await page.keyboard.press('Escape')
    await wait(500)
    assert.equal(await panelWidth(page, 'tree'), treeWidth)
    await clickButton(page, 'Maximise preview')
    await clickButton(page, 'Restore panels')
    assert.equal(await panelWidth(page, 'tree'), treeWidth)
  })

  uiTest(session, 'Desktop and mobile previews side by side both follow the selection', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme, { clearWorkspace: true })

    await pickPreviewOption(page, 'Desktop and mobile')
    await page.waitForSelector('[data-preview-device="mobile"] iframe[data-preview-frame="visible"]', {
      timeout: 30000,
    })
    const desktop = await visibleFrame(page, 'desktop')
    const mobile = await visibleFrame(page, 'mobile')
    assert.equal(await desktop.evaluate(() => window.innerWidth), 1280)
    assert.equal(await mobile.evaluate(() => window.innerWidth), 390)

    const canvas = await box(page, '[data-preview-canvas]')
    const desktopBox = await box(page, '[data-preview-device="desktop"]')
    const mobileBox = await box(page, '[data-preview-device="mobile"]')
    assert.ok(desktopBox.x >= canvas.x && mobileBox.x + mobileBox.width <= canvas.x + canvas.width + 1, 'both frames fit')

    const desktopScroll = await desktop.evaluate(() => window.scrollY)
    await wheelOver(page, 'mobile')
    assert.ok((await mobile.evaluate(() => window.scrollY)) > 0, 'the mobile page scrolls')
    assert.equal(await desktop.evaluate(() => window.scrollY), desktopScroll, 'the desktop page stays where it was')

    await page.click('[data-tree-node^="section:"]')
    await wait(800)
    assert.ok(await outlineShown(desktop), 'desktop highlights the picked section')
    assert.ok(await outlineShown(mobile), 'mobile highlights the picked section')

    const picked = await mobile.evaluate(() => {
      const sections = document.querySelectorAll('[data-commera-section]')
      const section = sections[sections.length - 1]
      section.click()
      return section.dataset.commeraSection
    })
    await wait(800)
    const selectedNode = await page.$eval('[data-tree-node][aria-current="true"]', (element) => element.dataset.treeNode)
    assert.ok(selectedNode?.includes(picked), `a click in the mobile preview selects ${picked} (got ${selectedNode})`)
    assert.ok(await outlineShown(desktop), 'the desktop preview follows a pick made on mobile')
  })

  uiTest(session, 'Desktop and mobile previews keep the same section at the top', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    await openEditor(page, theme, { clearWorkspace: true })

    const target = await page.$$eval('[data-tree-node^="section:index:"]', (nodes) => {
      const deals = nodes.find((node) => node.innerText.trim().startsWith('Deals'))
      return (deals ?? nodes[nodes.length - 2])?.dataset.treeNode
    })
    if (!target) return t.skip('the home page has too few sections to scroll between')
    const [, group, section] = target.split(':')

    await pickPreviewOption(page, 'Desktop and mobile')
    await page.waitForSelector('[data-preview-device="mobile"] iframe[data-preview-frame="visible"]', {
      timeout: 30000,
    })
    await wait(1000)
    const desktop = await visibleFrame(page, 'desktop')
    const mobile = await visibleFrame(page, 'mobile')
    const sectionTop = (frame) =>
      frame.evaluate(
        (group, section) =>
          document
            .querySelector(`[data-commera-group="${group}"][data-commera-section="${section}"]`)
            .getBoundingClientRect().top,
        group,
        section,
      )
    const scrollDesktopToTarget = () =>
      desktop.evaluate(
        (group, section) => {
          const element = document.querySelector(`[data-commera-group="${group}"][data-commera-section="${section}"]`)
          window.scrollTo({ top: element.getBoundingClientRect().top + window.scrollY, behavior: 'instant' })
        },
        group,
        section,
      )

    await scrollDesktopToTarget()
    await wait(800)
    assert.ok(Math.abs(await sectionTop(desktop)) <= 2, `desktop shows ${section} at the top`)
    assert.ok(Math.abs(await sectionTop(mobile)) <= 2, `mobile follows to ${section} (top ${await sectionTop(mobile)})`)
  })

  uiTest(session, 'Typing Arabic over a default text keeps the English default', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')
    const editorData = await adminGet(page, 'theme_layout.get_editor', { theme: theme.name, page: 'index' })
    const schema = editorData.section_schemas.find(
      (candidate) =>
        (candidate.groups ?? ['pages']).includes('pages') &&
        candidate.settings?.some((setting) => setting.type === 'text' && setting.default),
    )
    if (!schema) return t.skip('no home page section has a text setting with a default')
    const setting = schema.settings.find((candidate) => candidate.type === 'text' && candidate.default)
    await openEditor(page, theme)

    const [addButton] = await page.$$(
      'xpath/.//button[normalize-space()="Add section" or @aria-label="Add section to Home page"]',
    )
    await addButton.click()
    await page.click(`[data-section-type="${schema.type}"]`)
    const input = `[data-settings-panel] #setting-${setting.id}`
    await page.waitForSelector(input, { visible: true })

    try {
      await pickPreviewOption(page, 'Right to left')
      await page.click(input)
      await page.keyboard.type('عرض خاص')
      await page.keyboard.press('Tab')
      await pickPreviewOption(page, 'Left to right')
      await wait(500)
      assert.equal(await page.$eval(input, (element) => element.value), setting.default)
    } finally {
      await pickPreviewOption(page, 'Left to right')
      await page.click('[data-settings-panel] button[aria-label="Remove section"]')
      await wait(500)
    }
  })

  uiTest(session, 'Switching page keeps unsaved theme settings, and leaving asks about them', async (t) => {
    const { page } = session
    const theme = await findLiveSectionsTheme(page)
    if (!theme) return t.skip('the live theme is not a Sections theme')

    // The page switch needs a second page. A theme with only a home page is given a stand-in
    // "Product" page answered from the home page's own data, which is enough for the editor.
    const home = await adminGet(page, 'theme_layout.get_editor', { theme: theme.name, page: 'index' })
    const pages = home.pages.includes('product') ? home.pages : [...home.pages, 'product']
    const onRequest = (request) => {
      if (request.isInterceptResolutionHandled()) return
      const url = new URL(request.url())
      if (!url.pathname.endsWith('theme_layout.get_editor')) return request.continue()
      // createAdminCaller POSTs, so the page rides in the body.
      const asked = JSON.parse(request.postData() || '{}').page ?? url.searchParams.get('page')
      if (asked !== 'index' && asked !== 'product') return request.continue()
      const body = { data: { ...home, pages, page: asked } }
      request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    }
    await page.setRequestInterception(true)
    page.on('request', onRequest)

    try {
      await openEditor(page, theme)
      await openThemeSettings(page)

      const field = await page.evaluate(() => {
        const input = [...document.querySelectorAll('input[id^="theme-"]')].find(
          (element) => element.type === 'text' && !element.readOnly && !element.disabled,
        )
        return input && { id: input.id, value: input.value }
      })
      if (!field) return t.skip('this theme has no editable text setting')
      const typed = `${field.value} E2E unsaved`
      await page.click(`#${field.id}`)
      await page.$eval(`#${field.id}`, (input) => input.select())
      await page.keyboard.type(typed)

      const trigger = await page.evaluateHandle(() =>
        [...document.querySelectorAll('[data-theme-layout-editor] header button')].find((button) =>
          button.querySelector('.lucide-chevron-down'),
        ),
      )
      await trigger.asElement().click()
      await wait(500)
      const option = await page.evaluateHandle(() =>
        [...document.querySelectorAll('[role=menuitem]')].find((item) => item.textContent.trim().startsWith('Product')),
      )
      assert.ok(option.asElement(), 'the page picker offers no Product page')
      await option.asElement().click()
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll('[data-theme-layout-editor] header button')].some((button) =>
            button.textContent.trim().startsWith('Product'),
          ),
        { timeout: 15000 },
      )
      await wait(800)
      assert.equal(await page.$eval(`#${field.id}`, (input) => input.value), typed, 'a page switch dropped the typed theme setting')

      // Leaving through the app asks before the typed setting is dropped, and Cancel stays.
      await page.click('[data-theme-layout-editor] header nav a, [data-theme-layout-editor] header a')
      await page.waitForFunction(() => document.body.innerText.includes('Discard unsaved theme settings?'), { timeout: 5000 })
      const cancel = await page.evaluateHandle(() =>
        [...document.querySelectorAll('[role=dialog] button')].find((button) => button.innerText.trim() === 'Cancel'),
      )
      await cancel.asElement().click()
      await wait(600)
      assert.ok(page.url().includes('/editor'), 'Cancel did not keep the editor open')
    } finally {
      page.off('request', onRequest)
      await page.setRequestInterception(false)
    }
  })
})
