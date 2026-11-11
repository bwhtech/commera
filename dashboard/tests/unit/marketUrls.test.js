import assert from 'node:assert/strict'
import { test } from 'node:test'
import { countryOwners, errorField, marketHreflang, marketUrls, urlSummary } from '../../src/data/marketUrls.js'

const CODES = { 'United Arab Emirates': 'AE', Oman: 'OM' }
const countryCode = (country) => CODES[country] ?? ''

test('a market answers on each language in each of its countries', () => {
  const market = { is_primary: false, languages: ['ar', 'en'], countries: ['United Arab Emirates', 'Oman'] }
  assert.deepEqual(
    marketUrls(market, { defaultLanguage: 'en', countryCode }).map(({ url, hreflang }) => [url, hreflang]),
    [
      ['/ar-ae/', 'ar-AE'],
      ['/ar-om/', 'ar-OM'],
      ['/en-ae/', 'en-AE'],
      ['/en-om/', 'en-OM'],
    ],
  )
})

test('the primary market uses the store language prefixes', () => {
  const market = { is_primary: true, languages: ['en', 'ar'], countries: [] }
  assert.deepEqual(
    marketUrls(market, { defaultLanguage: 'en', countryCode }).map(({ url, hreflang }) => [url, hreflang]),
    [
      ['/', 'en'],
      ['/ar/', 'ar'],
    ],
  )
})

test('a country without a code has no URL yet', () => {
  const market = { is_primary: false, languages: ['en'], countries: ['Atlantis'] }
  assert.deepEqual(marketUrls(market, { defaultLanguage: 'en', countryCode }), [])
})

test('a script language keeps its script in the hreflang', () => {
  assert.equal(marketHreflang('zh-hans', 'ae'), 'zh-Hans-AE')
})

test('a row shows two URLs and counts the rest', () => {
  const urls = ['/en-ae/', '/ar-ae/', '/en-om/', '/ar-om/'].map((url) => ({ url }))
  assert.equal(urlSummary(urls), '/en-ae/ /ar-ae/ +2')
  assert.equal(urlSummary(urls.slice(0, 2)), '/en-ae/ /ar-ae/')
})

test('the countries of the other markets name their market', () => {
  const markets = [
    { handle: 'gulf', market_name: 'Gulf', countries: ['Oman'] },
    { handle: 'uae', market_name: 'UAE', countries: ['United Arab Emirates'] },
  ]
  assert.deepEqual([...countryOwners(markets, 'uae')], [['Oman', 'Gulf']])
})

test('a refusal carries its field independently of its title', () => {
  assert.equal(errorField({ field: 'compare_at_price_list', title: 'Invalid Price List' }), 'compare_at_price_list')
  assert.equal(errorField({ field: 'sale_price_list', title: 'Invalid Price List' }), 'sale_price_list')
  assert.equal(errorField({ title: 'Invalid Price List' }), null)
  assert.equal(errorField(null), null)
})
