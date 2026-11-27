import assert from 'node:assert/strict'
import { test } from 'node:test'
import { changedFields, rebaseDraft, storedDraft } from '../../src/data/productDraft.js'

const fields = ['title', 'description', 'collections']
const server = (overrides = {}) => ({ title: 'Tee', description: null, collections: ['Shirts'], ...overrides })

test('a freshly loaded product has nothing to save', () => {
  const stored = storedDraft(server(), fields)
  assert.deepEqual(changedFields({ ...stored }, stored), [])
})

test('an empty editor and a stored null description are the same', () => {
  const stored = storedDraft(server(), fields)
  assert.deepEqual(changedFields({ ...stored, description: '<p></p>' }, stored), [])
})

test('a number input answering text is not an edit', () => {
  const stored = storedDraft({ price: 25 }, ['price'])
  assert.deepEqual(changedFields({ price: '25' }, stored), [])
})

test('an edited title is reported as changed', () => {
  const stored = storedDraft(server(), fields)
  assert.deepEqual(changedFields({ ...stored, title: 'Tee v2' }, stored), ['title'])
})

test('a reload after a variant save keeps the unsaved title', () => {
  const previous = storedDraft(server(), fields)
  const draft = { ...previous, title: 'Unsaved title' }
  const next = storedDraft(server(), fields)
  assert.equal(rebaseDraft(draft, previous, next).title, 'Unsaved title')
})

test('a reload adopts server changes to fields the merchant did not touch', () => {
  const previous = storedDraft(server(), fields)
  const draft = { ...previous, title: 'Unsaved title' }
  const next = storedDraft(server({ collections: ['Shirts', 'Sale'] }), fields)
  const rebased = rebaseDraft(draft, previous, next)
  assert.deepEqual(rebased.collections, ['Shirts', 'Sale'])
  assert.equal(rebased.title, 'Unsaved title')
})

test('after a save the reloaded answer becomes the clean draft', () => {
  const saved = { title: 'Tee v2', description: '<p>Soft</p>', collections: ['Shirts'] }
  const next = storedDraft(server({ title: 'Tee v2', description: '<p>Soft</p>' }), fields)
  const rebased = rebaseDraft(saved, saved, next)
  assert.deepEqual(changedFields(rebased, next), [])
})

test('the adopted collections are a copy, not the stored array', () => {
  const previous = storedDraft(server(), fields)
  const next = storedDraft(server(), fields)
  const rebased = rebaseDraft({ ...previous }, previous, next)
  rebased.collections.push('Sale')
  assert.deepEqual(next.collections, ['Shirts'])
})
