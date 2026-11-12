import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  fieldKey,
  groupResources,
  groupSections,
  isEmptyResource,
  itemProgress,
  languageChoices,
  languageTotals,
  parseFieldKey,
  progressStatus,
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

test('a record counts its unsaved values as done until saved', () => {
  const item = {
    name: 'blue-shirt',
    fields: [
      { field: 'title', kind: 'text', status: 'missing' },
      { field: 'description', kind: 'html', status: 'outdated', value: 'Old' },
      { field: 'image', kind: 'image', status: 'current' },
      { field: 'note', kind: 'text', status: 'current', source_empty: true, value: 'Gone' },
    ],
  }
  const key = (field) => fieldKey('ar', 'product', 'blue-shirt', field)

  assert.deepEqual(itemProgress(item, {}, 'ar', 'product'), { toDo: 2, outdated: true, unsaved: 0 })
  // "Still correct" keeps the outdated value; the other field is still missing.
  const stillCorrect = itemProgress(item, { [key('description')]: 'Old' }, 'ar', 'product')
  assert.deepEqual(stillCorrect, { toDo: 1, outdated: false, unsaved: 1 })
  assert.equal(progressStatus(stillCorrect), 'unsaved')
  const cleared = itemProgress(item, { [key('title')]: 'عنوان', [key('description')]: '', [key('image')]: '', [key('note')]: '' }, 'ar', 'product')
  assert.deepEqual(cleared, { toDo: 1, outdated: false, unsaved: 4 })
  assert.equal(progressStatus(itemProgress(item, {}, 'fr', 'product')), 'outdated')
})

test('the status dot shows unsaved first, then outdated, missing or done', () => {
  assert.equal(progressStatus({ toDo: 2, outdated: true, unsaved: 1 }), 'unsaved')
  assert.equal(progressStatus({ toDo: 2, outdated: true, unsaved: 0 }), 'outdated')
  assert.equal(progressStatus({ toDo: 1, outdated: false, unsaved: 0 }), 'missing')
  assert.equal(progressStatus({ toDo: 0, outdated: false, unsaved: 0 }), 'current')
})

test('a resource without source text is empty, not done', () => {
  assert.equal(isEmptyResource({ missing: 0, outdated: 0, current: 0 }), true)
  assert.equal(isEmptyResource({ missing: 0, outdated: 0, current: 2 }), false)
})

test('the language menu marks a hidden language and counts its work', () => {
  const choices = languageChoices(
    [{ code: 'ar', name: 'Arabic', published: true }, { code: 'hi', name: 'Hindi', published: false }],
    { ar: { product: { missing: 2, outdated: 1, current: 0 } }, hi: {} },
  )

  assert.deepEqual(choices, [
    { code: 'ar', label: 'Arabic · 3 to do', hidden: false },
    { code: 'hi', label: 'Hindi · 0 to do', hidden: true },
  ])
})
