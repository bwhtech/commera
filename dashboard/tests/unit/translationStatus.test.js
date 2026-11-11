import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  fieldKey,
  groupResources,
  groupSections,
  languageTotals,
  parseFieldKey,
  toDoCount,
} from '../../src/data/translationStatus.js'

test('resources sit in the picker groups in order, a plugin resource under Other', () => {
  const groups = groupResources([
    { type: 'shop', label: 'Shop' },
    { type: 'product', label: 'Products' },
    { type: 'recipe', label: 'Recipes' },
    { type: 'collection', label: 'Collections' },
  ])

  assert.deepEqual(
    groups.map((group) => [group.key, group.resources.map((resource) => resource.type)]),
    [
      ['catalog', ['product', 'collection']],
      ['settings', ['shop']],
      ['other', ['recipe']],
    ],
  )
  assert.equal(groups[2].resources[0].one, 'Recipes')
})

test('search engine and image fields get their own cards', () => {
  const sections = groupSections(
    [
      { field: 'display_name', kind: 'text' },
      { field: 'meta_title', kind: 'text' },
      { field: 'gif_1', kind: 'image' },
      { field: 'description', kind: 'html' },
    ],
    'Product',
  )

  assert.deepEqual(
    sections.map((section) => [section.title, section.fields.map((field) => field.field)]),
    [
      ['Product', ['display_name', 'description']],
      ['Search engine listing', ['meta_title']],
      ['Media', ['gif_1']],
    ],
  )
})

test('a language adds up its resources, and nothing to translate is done', () => {
  const totals = languageTotals({
    product: { missing: 3, outdated: 1, current: 4 },
    shop: { missing: 0, outdated: 1, current: 1 },
  })

  assert.deepEqual(totals, { missing: 3, outdated: 2, current: 5, percent: 50 })
  assert.equal(toDoCount(totals), 5)
  assert.equal(languageTotals({}).percent, 100)
})

test('a field key round-trips names holding any character', () => {
  const key = fieldKey('ar', 'theme_section', 'index/hero "1"', 'heading')

  assert.deepEqual(parseFieldKey(key), { language: 'ar', resource: 'theme_section', name: 'index/hero "1"', field: 'heading' })
})

test('pending field keys isolate languages', () => {
  assert.notEqual(fieldKey('ar', 'product', 'same', 'title'), fieldKey('fr', 'product', 'same', 'title'))
})
