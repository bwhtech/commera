// Read-only lane: every route must render its own screen, with no console errors
// and no failing request. Nothing here writes to the store.
import assert from 'node:assert/strict'
import { describe } from 'node:test'
import { goto, realProblems, text, uiTest, useSession } from './harness.js'

// route -> a string that only that screen renders, so "it loaded" cannot be
// satisfied by the shell alone.
const ROUTES = [
  ['/', 'Overview'],
  ['/orders', 'Orders'],
  ['/products', 'Products'],
  ['/collections', 'Collections'],
  ['/product-types', 'Product types'],
  ['/attributes', 'Attributes'],
  ['/inventory', 'Stock'],
  ['/inventory/adjustments', 'Adjustments'],
  ['/pricing', 'Edit prices'],
  ['/customers', 'Customers'],
  ['/analytics/revenue', 'Revenue'],
  ['/analytics/inventory', 'Inventory'],
  ['/analytics/storefront', 'Storefront'],
  ['/storefront/theme', 'Themes'],
  ['/storefront/navigation', 'Navigation'],
  ['/storefront/pages', 'Pages'],
]

describe('smoke', () => {
  const session = useSession()

  for (const [route, marker] of ROUTES) {
    uiTest(session, `renders ${route}`, async () => {
      await goto(session.page, route)
      const body = await text(session.page)
      assert.ok(body.includes(marker), `${route} did not render "${marker}"; body starts: ${body.slice(0, 200)}`)
      assert.deepEqual(realProblems(session.problems), [], `${route} reported browser problems`)
    }, { timeout: 60000 })
  }
})
