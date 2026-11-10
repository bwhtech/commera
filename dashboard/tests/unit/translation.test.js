import assert from 'node:assert/strict'
import { test } from 'node:test'
import { __ as bootTranslator, createTranslator } from '../../src/data/translation.js'

const __ = createTranslator({
  Orders: 'الطلبات',
  '{0} of {1} selected': 'تم تحديد {0} من {1}',
  'Draft:Order status': 'مسودة',
  Draft: 'تصميم',
})

test('a known string comes back translated', () => {
  assert.equal(__('Orders'), 'الطلبات')
})

test('an unknown string falls back to the English source', () => {
  assert.equal(__('Customers'), 'Customers')
})

test('placeholders fill in from the replacements, translated or not', () => {
  assert.equal(__('{0} of {1} selected', [2, 5]), 'تم تحديد 2 من 5')
  assert.equal(__('{0} products', [12]), '12 products')
})

test('a placeholder without a replacement stays visible', () => {
  assert.equal(__('{0} of {1} selected', [2]), 'تم تحديد 2 من {1}')
  assert.equal(__('Page {0}'), 'Page {0}')
})

test('a context picks its own translation, else the bare string', () => {
  assert.equal(__('Draft', null, 'Order status'), 'مسودة')
  assert.equal(__('Draft', null, 'Blog post'), 'تصميم')
})

test('an empty or non-string message passes through untouched', () => {
  assert.equal(__(''), '')
  assert.equal(__(null), null)
  assert.equal(__(undefined), undefined)
})

test('with no boot translations the shell reads in English', () => {
  assert.equal(bootTranslator('Orders'), 'Orders')
  assert.equal(bootTranslator('{0} orders', [3]), '3 orders')
})
