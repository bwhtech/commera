import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSequence } from '../../src/utils/sequence.js'
import { bulkSummary, runEach } from '../../src/utils/runEach.js'

test('createSequence lets only the newest ticket write', () => {
  const sequence = createSequence()
  const first = sequence.next()
  const second = sequence.next()
  assert.equal(sequence.isLatest(first), false)
  assert.equal(sequence.isLatest(second), true)
  sequence.cancel()
  assert.equal(sequence.isLatest(second), false)
})

test('a write started on the current ticket is dropped once a new load starts', () => {
  const sequence = createSequence()
  sequence.next()
  const save = sequence.current()
  assert.equal(sequence.isLatest(save), true)
  sequence.next()
  assert.equal(sequence.isLatest(save), false)
})

test('runEach keeps going past a refusal and reports which items failed', async () => {
  const order = []
  const refusal = new Error('ValidationError: Order is closed')
  const result = await runEach(['a', 'b', 'c', 'd'], async (item) => {
    order.push(item)
    if (item === 'b') throw refusal
    if (item === 'c') return false
    return null
  })
  assert.deepEqual(order, ['a', 'b', 'c', 'd'])
  assert.deepEqual(result.done, ['a', 'd'])
  assert.deepEqual(result.failed, [
    { item: 'b', error: refusal },
    { item: 'c', error: null },
  ])
})

test('runEach runs one write at a time', async () => {
  let running = 0
  let peak = 0
  await runEach([1, 2, 3], async () => {
    running += 1
    peak = Math.max(peak, running)
    await new Promise((resolve) => setTimeout(resolve, 5))
    running -= 1
  })
  assert.equal(peak, 1)
})

test('bulkSummary names the partial failure and its first reason', () => {
  assert.equal(bulkSummary({ done: ['a', 'b'], failed: [] }, 'order', 'marked fulfilled'), '2 orders marked fulfilled')
  assert.equal(bulkSummary({ done: ['a'], failed: [] }, 'order', 'marked fulfilled'), '1 order marked fulfilled')
  assert.equal(
    bulkSummary(
      { done: ['a'], failed: [{ item: 'b', error: null }, { item: 'c', error: new Error('Closed') }] },
      'order',
      'marked fulfilled',
    ),
    '1 of 3 orders marked fulfilled. 2 failed: Closed',
  )
  assert.equal(bulkSummary({ done: [], failed: [{ item: 'b', error: null }] }, 'product', 'archived'), '0 of 1 product archived. 1 failed')
  assert.equal(bulkSummary({ done: ['a', 'b'], failed: [] }, ['delivery', 'deliveries'], 'queued'), '2 deliveries queued')
})
