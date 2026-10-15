// Write lane over the two storefront editors that are actually wired to a backend:
// the main navigation tree and the footer columns.
//
// Storefront > Theme and Storefront > Pages are deliberately absent: both are still
// mock screens with no endpoint behind them, so there is no persisted state to assert.
import assert from 'node:assert/strict'
import { describe } from 'node:test'
import {
  PREFIX,
  adminGet,
  adminPost,
  clickByText,
  goto,
  onCleanup,
  realProblems,
  text,
  uiTest,
  useSession,
  wait,
} from './harness.js'

const NAV_ENTRY = `${PREFIX} Nav`
const FOOTER_COLUMN = `${PREFIX} Column`
const FOOTER_RENAMED = `${PREFIX} Column Renamed`

const created = { nodes: [], sections: [] }

async function openFooterTab(page) {
  await goto(page, '/storefront/navigation')
  await clickByText(page, 'button', 'Footer', { pause: 1500 })
}

// The ellipsis button lives inside the row, so it is found by the row's own label
// rather than by position — rows move as soon as anything is added above them.
async function openRowMenu(page, label, ariaLabel) {
  const handle = await page.evaluateHandle(
    (needle, aria) => {
      const buttons = Array.from(document.querySelectorAll(`button[aria-label="${aria}"]`))
      return buttons.find((button) => {
        const row = button.closest('div, li')
        const container = row?.parentElement?.closest('div') ?? row
        return (container?.innerText || '').trim().split('\n')[0] === needle
      })
    },
    label,
    ariaLabel,
  )
  const element = handle.asElement()
  if (!element) throw new Error(`no "${ariaLabel}" menu for row "${label}"`)
  await element.click()
  await wait(700)
}

async function typeIntoDialog(page, value) {
  const input = await page.$('[role="dialog"] input')
  if (!input) throw new Error('the dialog has no text field')
  await input.click({ clickCount: 3 })
  await page.keyboard.type(value, { delay: 15 })
}

describe('storefront', () => {
  const session = useSession()

  onCleanup(session, async ({ page }) => {
    for (const name of created.nodes) {
      await adminPost(page, 'navigation.delete_node', { name }).catch(() => {})
    }
    for (const name of created.sections) {
      await adminPost(page, 'footer.delete_section', { name }).catch(() => {})
    }
  })

  uiTest(session, 'adds and deletes a navigation section', async () => {
    const { page } = session
    await goto(page, '/storefront/navigation')

    await clickByText(page, 'button', 'Add section', { pause: 900 })
    await typeIntoDialog(page, NAV_ENTRY)
    await clickByText(page, '[role="dialog"] button', 'Add', { pause: 2000 })

    // Reload before asserting: an entry that only exists in the client's copy of the
    // tree looks identical on screen to one the server accepted.
    await goto(page, '/storefront/navigation')
    assert.ok((await text(page)).includes(NAV_ENTRY), 'the new section did not survive a reload')

    const menu = await adminGet(page, 'navigation.get_editor_data')
    const node = menu.menu.find((row) => row.label === NAV_ENTRY)
    assert.ok(node, 'the new section is not in the persisted menu')
    created.nodes.push(node.name)

    await openRowMenu(page, NAV_ENTRY, 'Entry actions')
    await clickByText(page, '[role="menuitem"]', 'Delete', { pause: 1200 })
    await clickByText(page, '[role="dialog"] button', 'Delete', { pause: 2000 })

    await goto(page, '/storefront/navigation')
    assert.ok(!(await text(page)).includes(NAV_ENTRY), 'the deleted section came back after a reload')
    const after = await adminGet(page, 'navigation.get_editor_data')
    assert.ok(!after.menu.some((row) => row.label === NAV_ENTRY), 'the section is still persisted')
    created.nodes.length = 0

    assert.deepEqual(realProblems(session.problems), [], 'the navigation editor reported browser problems')
  })

  uiTest(session, 'draws an icon on every editor menu item', async () => {
    const { page } = session
    const missing = []
    const menus = [
      { open: () => goto(page, '/storefront/navigation'), aria: 'Entry actions' },
      { open: () => openFooterTab(page), aria: 'Column actions' },
      { open: () => openFooterTab(page), aria: 'Link actions' },
    ]
    for (const menu of menus) {
      await menu.open()
      const trigger = await page.$(`button[aria-label="${menu.aria}"]`)
      assert.ok(trigger, `no "${menu.aria}" menu on screen`)
      await trigger.click()
      await wait(700)
      const items = await page.$$eval('[role="menuitem"]', (nodes) =>
        nodes.map((node) => ({ label: node.innerText.trim(), icon: Boolean(node.querySelector('svg, [class*="lucide-"]')) })),
      )
      assert.ok(items.length, `the "${menu.aria}" menu opened empty`)
      missing.push(...items.filter((item) => !item.icon).map((item) => `${menu.aria}: ${item.label}`))
      await page.keyboard.press('Escape')
    }
    assert.deepEqual(missing, [], 'menu items without an icon')
  })

  uiTest(session, 'adds, renames and deletes a footer column', async () => {
    const { page } = session
    await openFooterTab(page)

    await clickByText(page, 'button', 'Add column', { pause: 900 })
    await typeIntoDialog(page, FOOTER_COLUMN)
    await clickByText(page, '[role="dialog"] button', 'Add', { pause: 2000 })

    await openFooterTab(page)
    assert.ok((await text(page)).includes(FOOTER_COLUMN), 'the new column did not survive a reload')
    let footer = await adminGet(page, 'footer.get_editor_data')
    const section = footer.columns.find((row) => row.title === FOOTER_COLUMN)
    assert.ok(section, 'the new column is not in the persisted footer')
    created.sections.push(section.name)

    await openRowMenu(page, FOOTER_COLUMN, 'Column actions')
    await clickByText(page, '[role="menuitem"]', 'Rename', { pause: 900 })
    await typeIntoDialog(page, FOOTER_RENAMED)
    await clickByText(page, '[role="dialog"] button', 'Rename', { pause: 2000 })

    await openFooterTab(page)
    footer = await adminGet(page, 'footer.get_editor_data')
    assert.ok(
      footer.columns.some((row) => row.title === FOOTER_RENAMED),
      'the rename was not persisted',
    )
    created.sections = footer.columns.filter((row) => row.title === FOOTER_RENAMED).map((row) => row.name)

    await openRowMenu(page, FOOTER_RENAMED, 'Column actions')
    await clickByText(page, '[role="menuitem"]', 'Delete column', { pause: 900 })
    await clickByText(page, '[role="dialog"] button', 'Delete column', { pause: 2000 })

    await openFooterTab(page)
    footer = await adminGet(page, 'footer.get_editor_data')
    assert.ok(
      !footer.columns.some((row) => row.title.startsWith(PREFIX)),
      'the deleted column is still persisted',
    )
    created.sections.length = 0

    assert.deepEqual(realProblems(session.problems), [], 'the footer editor reported browser problems')
  })
})
