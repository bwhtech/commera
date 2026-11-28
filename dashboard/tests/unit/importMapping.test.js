import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileSize, isSameMapping, missingFields, remapColumn, stillNeeded, suggestionParams } from '../../src/data/importMapping.js'

test('title and price are required, and collection only without a collection for every row', () => {
  assert.deepEqual(missingFields({ Name: 'title' }, ''), ['sale_price', 'collection'])
  assert.deepEqual(missingFields({ Name: 'title', Cost: 'sale_price' }, 'Candles'), [])
  assert.deepEqual(missingFields({ Name: 'title', Cost: 'sale_price', Group: 'collection' }, ''), [])
})

test('color and size are never required', () => {
  assert.deepEqual(missingFields({ Name: 'title', Price: 'sale_price', Type: 'collection' }, ''), [])
})

test('picking a field another column has moves it, so each field is read from one column', () => {
  assert.deepEqual(remapColumn({ Price: 'sale_price', MRP: '' }, 'MRP', 'sale_price'), { Price: '', MRP: 'sale_price' })
  assert.deepEqual(remapColumn({ Price: 'sale_price', MRP: 'compare_at_price' }, 'MRP', ''), { Price: 'sale_price', MRP: '' })
})

test('an unmapped column and a missing one are the same mapping', () => {
  assert.equal(isSameMapping({ Price: 'sale_price', Handle: '' }, { Price: 'sale_price' }), true)
  assert.equal(isSameMapping({ Price: '' }, { Price: 'sale_price' }), false)
  assert.equal(isSameMapping({ Price: 'sale_price' }, null), false)
})

test('a file under 1 KB never reads as 0 KB', () => {
  assert.equal(fileSize(200), '<1 KB')
  assert.equal(fileSize(2048), '2 KB')
  assert.equal(fileSize(3 * 1024 * 1024), '3.0 MB')
})

test('a field the last check reported missing stays needed, so Continue never opens on an empty review', () => {
  assert.deepEqual(stillNeeded({ Name: 'title', Price: 'sale_price' }, 'Candles', ['collection']), ['collection'])
  assert.deepEqual(stillNeeded({ Name: 'title' }, 'Candles', ['sale_price']), ['sale_price'])
  assert.deepEqual(stillNeeded({ Name: 'title', Price: 'sale_price' }, 'Candles'), [])
})

test('our suggestions keep the collection picked for every row', () => {
  assert.deepEqual(suggestionParams('/files/a.csv', 'Candles'), { file_url: '/files/a.csv', default_collection: 'Candles' })
  assert.deepEqual(suggestionParams('/files/a.csv', ''), { file_url: '/files/a.csv' })
})
