// Write lane: the catalog screens that create real rows — collections, attributes,
// and the add-product dialog with its option x size grid.
import assert from 'node:assert/strict'
import { describe } from 'node:test'
import {
  PREFIX,
  adminGet,
  adminPost,
  apiPost,
  clickByText,
  deleteResource,
  goto,
  listResource,
  onCleanup,
  realProblems,
  text,
  typeInto,
  uiTest,
  updateResource,
  useSession,
  wait,
} from './harness.js'

const COLLECTION = `${PREFIX} Collection`
const ATTRIBUTE = `${PREFIX}Fabric`
const PRODUCT = `${PREFIX} Tee`
const REVIEW = `${PREFIX} Review`

const created = { products: [], collections: [], attributes: [] }

// frappe-ui's dialog.prompt labels its confirm button per screen, so the button is
// found by whichever of the known confirm labels this prompt actually rendered.
const CONFIRM_LABELS = ['Create', 'Submit', 'Confirm', 'Save']

async function confirmPrompt(page) {
  const labels = await page.$$eval('[role="dialog"] button', (nodes) => nodes.map((node) => node.innerText.trim()))
  const label = CONFIRM_LABELS.find((candidate) => labels.includes(candidate))
  if (!label) throw new Error('no confirm button in the prompt dialog, only: ' + labels.join(', '))
  await clickByText(page, '[role="dialog"] button', label, { pause: 1800 })
}

async function typeIntoDialog(page, index, value) {
  const inputs = await page.$$('[role="dialog"] input')
  if (!inputs[index]) throw new Error(`the dialog has no field ${index}`)
  await inputs[index].click()
  await inputs[index].type(value, { delay: 15 })
}

// A collection the store already files products under, so cleanup never has to guess
// whether an arbitrary Item Group is a legal home for an item.
async function fallbackCollection(page, exclude) {
  const { products } = await adminGet(page, 'catalog.get_products', { page_length: 50 })
  // Never another run's leftover collection: that would just move the junk sideways.
  const found = products.find((row) => row.collection && row.collection !== exclude && !row.collection.startsWith('E2E-'))
  if (!found) throw new Error('no existing collection to move the run\'s items into')
  return found.collection
}

describe('catalog', () => {
  const session = useSession()

  onCleanup(session, async ({ page }) => {
    // Products can never be hard-deleted: the Style Attribute Configurator holds live links
    // to their variants. Archiving is exactly what the UI's Archive action does.
    for (const item of created.products) {
      await adminPost(page, 'catalog.update_product', { item_template: item, disabled: 1 }).catch(() => {})
    }
    // Those archived rows still link the run's collection, and an Item Group with any link
    // left cannot be deleted. Both doctypes that carry an item_group have to be moved to a
    // collection the store already used before the group itself can go.
    for (const name of created.collections) {
      const fallback = await fallbackCollection(page, name)
      for (const doctype of ['Item', 'Style Attribute Variant']) {
        for (const row of await listResource(page, doctype, { item_group: name })) {
          await updateResource(page, doctype, row.name, { item_group: fallback }).catch(() => {})
        }
      }
      await deleteResource(page, 'Item Group', name).catch((error) => console.error(error.message))
    }
    for (const name of created.attributes) {
      await deleteResource(page, 'Item Attribute', name).catch((error) => console.error(error.message))
    }
  })

  uiTest(session, 'creates a collection', async () => {
    const { page } = session
    await goto(page, '/collections')
    await clickByText(page, 'button', 'Create collection', { pause: 900 })
    await typeIntoDialog(page, 0, COLLECTION)
    await confirmPrompt(page)
    created.collections.push(COLLECTION)

    const collections = await adminGet(page, 'catalog.get_collections')
    assert.ok(collections.includes(COLLECTION), `${COLLECTION} was not persisted; got ${collections.join(', ')}`)
    assert.ok((await text(page)).includes(COLLECTION), 'the new collection did not appear in the list')
  })

  uiTest(session, 'publishes a review from its row without opening it', async () => {
    const { page } = session
    const [variant] = await listResource(page, 'Style Attribute Variant', {}, ['name', 'item_style'])
    assert.ok(variant, 'the store has no product to review')
    const review = await apiPost(page, 'frappe.client.insert', {
      doc: { doctype: 'Product Review', variant: variant.name, item_style: variant.item_style, rating: 4, review_title: REVIEW },
    })
    onCleanup(session, ({ page: cleanupPage }) => deleteResource(cleanupPage, 'Product Review', review.name).catch(() => {}))

    await goto(page, '/reviews')
    const toggle = await page.evaluateHandle((title) => {
      const row = Array.from(document.querySelectorAll('a, [role="row"], li, div')).find(
        (node) => node.querySelector('[role="switch"]') && node.innerText.includes(title) && node.querySelectorAll('[role="switch"]').length === 1,
      )
      return row?.querySelector('[role="switch"]')
    }, REVIEW)
    assert.ok(toggle.asElement(), 'the new review has no publish switch in the list')
    await toggle.asElement().click()
    await wait(1500)

    assert.ok(page.url().endsWith('/reviews'), `the switch opened ${page.url()} instead of staying on the list`)
    const { reviews } = await adminGet(page, 'reviews.get_reviews', { tab: 'published', search: REVIEW })
    assert.ok(reviews.some((row) => row.name === review.name), 'the switch did not publish the review')

    await clickByText(page, 'p', REVIEW, { pause: 1500 })
    assert.ok(page.url().endsWith(`/reviews/${review.name}`), `clicking the row opened ${page.url()}`)
    assert.deepEqual(realProblems(session.problems), [], 'the reviews list reported browser problems')
  })

  uiTest(session, 'opens an attribute to edit its values', async () => {
    const { page } = session
    const [attribute] = await adminGet(page, 'catalog.get_attributes')
    assert.ok(attribute?.values?.length, 'the store has no attribute with values to open')

    await goto(page, '/attributes')
    await clickByText(page, 'button', 'Edit', { pause: 1200 })
    const dialog = await page.$eval('[role="dialog"]', (node) => node.innerText).catch(() => '')
    assert.ok(dialog.includes(attribute.name), 'Edit did not open the attribute dialog')
    assert.ok(dialog.includes(attribute.values[0].value), 'the dialog does not list the attribute values')
    assert.deepEqual(realProblems(session.problems), [], 'the attribute dialog reported browser problems')
  })

  uiTest(session, 'creates an attribute with values', async () => {
    const { page } = session
    await goto(page, '/attributes')
    await clickByText(page, 'button', 'New attribute', { pause: 900 })
    await typeIntoDialog(page, 0, ATTRIBUTE)
    await typeIntoDialog(page, 1, 'Linen, Denim')
    await confirmPrompt(page)
    created.attributes.push(ATTRIBUTE)

    const attributes = await adminGet(page, 'catalog.get_attributes')
    const saved = attributes.find((row) => row.name === ATTRIBUTE)
    assert.ok(saved, `${ATTRIBUTE} was not persisted`)
    assert.deepEqual(saved.values, ['Linen', 'Denim'])
  })

  uiTest(
    session,
    'creates a product from the option and size grid',
    async () => {
      const { page } = session
      await goto(page, '/products')
      await clickByText(page, 'button', 'Add product', { pause: 1200 })
      await typeInto(page, 'Cotton oversized tee', PRODUCT)

      await clickByText(page, 'button', 'Select a collection', { pause: 800 })
      await clickByText(page, '[role="option"]', COLLECTION, { pause: 600 })

      await clickByText(page, 'button', 'Pick or type a color', { pause: 800 })
      for (const colour of ['Red', 'Blue']) await clickByText(page, '[role="option"]', colour, { pause: 350 })
      await page.keyboard.press('Escape')
      await wait(500)

      await clickByText(page, 'button', 'Pick or type a size', { pause: 800 })
      for (const size of ['S', 'M', 'L']) await clickByText(page, '[role="option"]', size, { pause: 350 })
      await page.keyboard.press('Escape')
      await wait(700)

      const body = await text(page)
      assert.ok(body.includes('6 variants will be created'), 'the grid summary did not count 2 x 3 variants')

      // Untick two cells so Blue ships in M only: the grid must drive what is created,
      // not merely decorate the option x size cross product.
      for (const cell of ['Blue in size S', 'Blue in size L']) {
        const box = await page.$(`[aria-label="${cell}"]`)
        assert.ok(box, `no grid checkbox for "${cell}"`)
        await box.click()
        await wait(250)
      }
      assert.ok((await text(page)).includes('4 variants will be created'), 'unticking did not change the count')

      // The page header carries an "Add product" button too, so the dialog's is the last match.
      await clickByText(page, 'button', 'Add product', { last: true, pause: 6000 })

      const match = page.url().match(/\/products\/([^/?#]+)$/)
      assert.ok(match, `expected to land on the product detail page, got ${page.url()}`)
      const itemTemplate = decodeURIComponent(match[1])
      created.products.push(itemTemplate)

      const product = await adminGet(page, 'catalog.get_product', { item_template: itemTemplate })
      assert.equal(product.title, PRODUCT)
      assert.equal(product.collection, COLLECTION)
      assert.equal(product.variants.length, 2, 'expected one variant per option')
      const bySize = Object.fromEntries(product.variants.map((row) => [row.option, row.sizes.length]))
      assert.deepEqual(bySize, { Red: 3, Blue: 1 }, 'the excluded grid cells were not honoured')

      assert.deepEqual(realProblems(session.problems), [], 'creating a product reported browser problems')
    },
    { timeout: 180000 },
  )
})
