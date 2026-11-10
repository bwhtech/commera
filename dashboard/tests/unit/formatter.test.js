import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const cases = JSON.parse(
  readFileSync(new URL('../../../packages/storefront/test/formatter-cases.json', import.meta.url)),
)

// boot.js reads `globalThis` once at import, so the boot keys are set before the module loads.
Object.assign(globalThis, {
  lang: 'ar',
  is_rtl: true,
  currency: 'INR',
  number_format: '#,###.##',
  currency_symbols: { INR: '₹', USD: '$' },
  money_formats: { INR: { number_format: '#,##,###.##', precision: 2 } },
  date_formats: cases.date_formats.ar,
})
const { compactMoney, count, exactMoney, formatDate, money, moneyIn, monthName, symbolFor } = await import(
  '../../src/data/formatter.js'
)

test('money reads the resolved currency format and puts the symbol after the amount in RTL', () => {
  assert.equal(money(1234567.6), '12,34,568\u00a0₹')
  assert.equal(exactMoney(499.99), '499.99\u00a0₹')
  assert.equal(exactMoney(500), '500\u00a0₹')
  assert.equal(moneyIn(1250.5, 'USD'), '1,250.50\u00a0$')
  assert.equal(moneyIn(10, 'AED'), '10\u00a0AED')
})

test('compact money takes its unit words from the admin language', () => {
  assert.equal(compactMoney(482300), '482.3\u00a0ألف\u00a0₹')
})

test('counts use the language number format, not Indian English', () => {
  assert.equal(count(1234567), '1,234,567')
  assert.equal(count(null), '0')
})

test('dates and month names follow the admin language', () => {
  assert.equal(formatDate('2026-12-01'), '01\u200f/12\u200f/2026')
  assert.equal(monthName(3), 'مارس')
})

test('symbolFor gives a bare symbol or code for an input prefix', () => {
  assert.equal(symbolFor(), '₹')
  assert.equal(symbolFor('AED'), 'AED')
})
