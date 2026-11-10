import assert from 'node:assert/strict'
import { test } from 'node:test'

// Intl's Persian default is the Solar Hijri calendar: January would read دی.
Object.assign(globalThis, { lang: 'fa', is_rtl: true })
const { monthName } = await import('../../src/data/formatter.js')

test('Persian month names stay Gregorian', () => {
  assert.equal(monthName(1), 'ژانویه')
  assert.equal(monthName(12), 'دسامبر')
})
