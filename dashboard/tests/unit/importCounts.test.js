import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  doneTitle,
  erpnextImportLabel,
  importLabel,
  notPublishedBody,
  photoGroupKind,
  photoGroupsHavePhoto,
  photoGroupsNeedPhoto,
  resultRowName,
  publishAllLabel,
  publishedBody,
  reviewSummary,
  showsOriginalPrice,
  visibleFilter,
} from '../../src/data/importCounts.js'

test('the import button counts products, and variants separately', () => {
  assert.equal(importLabel({ products: 1, variants: 6 }), 'Import 1 product (6 variants)')
  assert.equal(importLabel({ products: 2, variants: 1 }), 'Import 2 products (1 variant)')
  assert.equal(importLabel({ products: 3, variants: 0 }), 'Import 3 products')
  assert.equal(importLabel({ products: 1, variants: 0 }), 'Import 1 product')
})

test('a review with every row skipped never offers to import 0 products', () => {
  assert.equal(importLabel({ products: 0, variants: 0 }), 'Nothing to import')
  assert.deepEqual(reviewSummary({ products: 0, variants: 0, warnings: 0, errors: 2 }), [{ label: '2 rows skipped', tone: 'error' }])
})

test('the original price is struck through only beside a valid lower price', () => {
  assert.equal(showsOriginalPrice({ sale_price: 500, compare_at_price: 650 }), true)
  assert.equal(showsOriginalPrice({ sale_price: 500, compare_at_price: 0 }), false)
  assert.equal(showsOriginalPrice({ sale_price: -5, compare_at_price: 0 }), false)
  assert.equal(showsOriginalPrice({ sale_price: 0, compare_at_price: 100 }), false)
})

test('the review summary names problems only when there are some', () => {
  assert.deepEqual(reviewSummary({ products: 1, variants: 3, warnings: 0, errors: 0 }), [{ label: '1 product' }, { label: '3 variants' }])
  assert.deepEqual(reviewSummary({ products: 2, variants: 0, warnings: 1, errors: 2 }), [
    { label: '2 products' },
    { label: '1 warning', tone: 'warning' },
    { label: '2 rows skipped', tone: 'error' },
  ])
})

test('a finished import says drafts until they are published', () => {
  assert.equal(doneTitle(1, null), '1 product added, not published yet')
  assert.equal(doneTitle(4, null), '4 products added, not published yet')
  assert.equal(doneTitle(0, null), 'No products were added')
  assert.equal(doneTitle(4, 4), '4 products are live')
})

test('a Publish all that published nothing says so instead of "0 products are live"', () => {
  assert.equal(doneTitle(2, 0), 'No products were published')
})

test('a review filter whose tab is gone falls back to all rows', () => {
  const options = [{ value: 'all' }, { value: 'ready' }]
  assert.equal(visibleFilter('errors', options), 'all')
  assert.equal(visibleFilter('ready', options), 'ready')
})

test('photo groups are counted as colors, or as products when nothing has a color', () => {
  assert.equal(photoGroupsNeedPhoto(2, 3, 'colors'), '2 of 3 colors still need a photo.')
  assert.equal(photoGroupsNeedPhoto(2, 4, 'products'), '2 of 4 products still need a photo.')
})

test('the verb agrees with the count in front of it', () => {
  assert.equal(photoGroupsNeedPhoto(1, 2, 'colors'), '1 of 2 colors still needs a photo.')
  assert.equal(photoGroupsNeedPhoto(1, 4, 'products'), '1 of 4 products still needs a photo.')
  assert.equal(photoGroupsHavePhoto(1, 2, 'colors'), '1 of 2 colors has a photo')
  assert.equal(photoGroupsHavePhoto(0, 2, 'colors'), '0 of 2 colors have a photo')
  assert.equal(photoGroupsHavePhoto(2, 3, 'products'), '2 of 3 products have a photo')
})

test('a batch of colored and plain products never calls a plain product a color', () => {
  const kind = photoGroupKind([{ color: 'Red' }, { color: '' }])
  assert.equal(kind, 'mixed')
  assert.equal(photoGroupsHavePhoto(1, 2, kind), '1 of 2 products and colors has a photo')
  assert.equal(photoGroupsNeedPhoto(1, 2, kind), '1 of 2 products and colors still needs a photo.')
  assert.equal(photoGroupKind([{ color: 'Red' }, { color: 'Blue' }]), 'colors')
  assert.equal(photoGroupKind([{ color: '' }]), 'products')
})

test('one photo group is counted in the singular', () => {
  assert.equal(photoGroupsNeedPhoto(1, 1, 'products'), '1 product still needs a photo.')
  assert.equal(photoGroupsNeedPhoto(1, 1, 'colors'), '1 color still needs a photo.')
  assert.equal(photoGroupsHavePhoto(1, 1, 'products'), '1 of 1 product has a photo')
})

test('a run result row is named by its number and its title', () => {
  assert.equal(resultRowName({ row: 6, title: 'Linen shirt' }), 'Row 6 · Linen shirt')
  assert.equal(resultRowName({ row: 6, title: '' }), 'Row 6')
})

test('the ERPNext pick button never offers to import 0 items', () => {
  assert.equal(erpnextImportLabel(0), 'Nothing to import')
  assert.equal(erpnextImportLabel(1), 'Import 1 item')
  assert.equal(erpnextImportLabel(4), 'Import 4 items')
})

test('the published line agrees with the number of live products', () => {
  assert.equal(publishedBody(1, 0), 'Customers can find it on your store now.')
  assert.equal(publishedBody(3, 0), 'Customers can find them on your store now.')
  assert.equal(publishedBody(0, 2), '2 products could not go live yet. Each one below says what it still needs.')
})

test('one imported product is offered as "it", with a plain Publish', () => {
  assert.equal(notPublishedBody(1), 'Publish it now, or later from its product page.')
  assert.equal(notPublishedBody(3), 'Publish them now, or later from each product page.')
  assert.equal(publishAllLabel(1), 'Publish')
  assert.equal(publishAllLabel(2), 'Publish all')
})
