import assert from 'node:assert/strict'
import { test } from 'node:test'
import { doneTitle, importLabel, reviewSummary } from '../../src/data/importCounts.js'

test('the import button counts products, and variants separately', () => {
  assert.equal(importLabel({ products: 1, variants: 6 }), 'Import 1 product (6 variants)')
  assert.equal(importLabel({ products: 2, variants: 1 }), 'Import 2 products (1 variant)')
  assert.equal(importLabel({ products: 3, variants: 0 }), 'Import 3 products')
  assert.equal(importLabel({ products: 1, variants: 0 }), 'Import 1 product')
})

test('the review summary names problems only when there are some', () => {
  assert.deepEqual(reviewSummary({ products: 1, variants: 3, warnings: 0, errors: 0 }), ['1 product', '3 variants'])
  assert.deepEqual(reviewSummary({ products: 2, variants: 0, warnings: 1, errors: 2 }), ['2 products', '1 warning', '2 rows skipped'])
})

test('a finished import says drafts until they are published', () => {
  assert.equal(doneTitle(1, null), '1 product added as a draft')
  assert.equal(doneTitle(4, null), '4 products added as drafts')
  assert.equal(doneTitle(0, null), 'No products were added')
  assert.equal(doneTitle(4, 4), '4 products are live')
})
