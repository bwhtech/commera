// Read-only lane over the day-to-day operating screens: the four lists and one
// order detail. Nothing here writes, so it is safe to run against a live store.
import assert from 'node:assert/strict'
import { describe } from 'node:test'
import { adminGet, clickByText, goto, realProblems, text, uiTest, useSession, wait } from './harness.js'

async function rowLinks(page, prefix) {
  return page.$$eval(
    `a[href^="/commera/${prefix}/"]`,
    (nodes) => Array.from(new Set(nodes.map((node) => node.getAttribute('href')))),
  )
}

describe('ops', () => {
  const session = useSession()

  uiTest(session, 'orders list filters and searches', async () => {
    const { page } = session
    await goto(page, '/orders')

    const { orders } = await adminGet(page, 'orders.get_orders', { status: 'all', page_length: 20 })
    assert.ok(orders.length, 'the store has no orders, so this spec cannot check the list')
    assert.ok((await text(page)).includes(orders[0].name), 'the first order from the API is not in the list')

    // Every status tab must answer with its own filtered set, not blow up.
    for (const tab of ['Unfulfilled', 'Unpaid', 'Open', 'Closed', 'All']) {
      await clickByText(page, 'button', tab, { pause: 900 })
      assert.deepEqual(realProblems(session.problems), [], `the ${tab} tab reported browser problems`)
    }

    const search = await page.$('input[placeholder="Search orders"]')
    assert.ok(search, 'the orders list has no search box')
    await search.click()
    await search.type(orders[0].name, { delay: 15 })
    await wait(1200)
    const links = await rowLinks(page, 'orders')
    assert.ok(
      links.some((href) => href.includes(orders[0].name)),
      `searching for ${orders[0].name} did not leave it in the list`,
    )
  })

  uiTest(session, 'opens an order detail', async () => {
    const { page } = session
    await goto(page, '/orders')
    const [first] = await rowLinks(page, 'orders')
    assert.ok(first, 'no order rows to open')
    const orderName = decodeURIComponent(first.split('/').pop())

    await goto(page, '/orders/' + encodeURIComponent(orderName))
    const body = await text(page)
    assert.ok(body.includes(orderName), 'the detail page does not name the order it opened')

    const order = await adminGet(page, 'orders.get_order', { sales_order: orderName })
    assert.ok(order.items.length, 'the order has no line items')
    assert.ok(body.includes(order.items[0].title), 'the first line item is not on the detail page')
    assert.deepEqual(realProblems(session.problems), [], 'the order detail reported browser problems')
  })

  uiTest(session, 'customers list opens a customer', async () => {
    const { page } = session
    await goto(page, '/customers')
    const { customers } = await adminGet(page, 'customers.get_customers', { page_length: 20 })
    assert.ok(customers.length, 'the store has no customers')
    assert.ok((await text(page)).includes(customers[0].name), 'the first customer is not in the list')

    await goto(page, '/customers/' + encodeURIComponent(customers[0].id))
    assert.ok((await text(page)).includes(customers[0].name), 'the customer detail did not render the customer')
    assert.deepEqual(realProblems(session.problems), [], 'the customer screens reported browser problems')
  })

  uiTest(session, 'list search boxes show their search icon', async () => {
    const { page } = session
    const missing = []
    for (const route of ['/orders', '/products', '/customers', '/inventory', '/reviews']) {
      await goto(page, route)
      const shown = await page.evaluate(() => {
        const icon = document.querySelector('input[placeholder^="Search"]')?.parentElement.querySelector('.lucide-search')
        return Boolean(icon?.getBoundingClientRect().width)
      })
      if (!shown) missing.push(route)
    }
    assert.deepEqual(missing, [], 'search boxes without their icon')
  })

  uiTest(session, 'revenue by-month table fills its card', async () => {
    const { page } = session
    await page.setViewport({ width: 1440, height: 900 })
    await goto(page, '/analytics/revenue')
    const gap = await page.evaluate(() => {
      const heading = Array.from(document.querySelectorAll('h2')).find((node) => node.innerText.trim() === 'By month')
      const section = heading?.closest('section')
      const lastColumn = Array.from(section?.querySelectorAll('*') ?? []).find(
        (node) => node.children.length === 0 && node.innerText?.trim() === 'Net',
      )
      let cell = lastColumn
      while (cell?.parentElement && getComputedStyle(cell.parentElement).display !== 'grid') cell = cell.parentElement
      if (!section || !cell?.parentElement) return null
      return section.getBoundingClientRect().right - cell.getBoundingClientRect().right
    })
    assert.ok(gap !== null, 'no By month table on the revenue report')
    assert.ok(gap < 48, `the table stops ${Math.round(gap)}px short of its card's edge`)
  })

  uiTest(session, 'inventory and pricing lists render their rows', async () => {
    const { page } = session

    await goto(page, '/inventory')
    const { rows: stockRows } = await adminGet(page, 'inventory.get_inventory', { page_length: 5 })
    assert.ok(stockRows.length, 'the store has no stock rows')
    assert.ok((await text(page)).includes(stockRows[0].item_code), 'the first stock row is not on screen')

    await goto(page, '/pricing')
    const { rows: priceRows } = await adminGet(page, 'catalog.get_pricing_rows', { page_length: 5 })
    assert.ok(priceRows.length, 'the store has no priceable items')
    assert.ok((await text(page)).includes(priceRows[0].title), 'the first price row is not on screen')
    assert.deepEqual(realProblems(session.problems), [], 'the inventory or pricing screens reported browser problems')
  })
})
