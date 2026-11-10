import { Formatter } from '../../../packages/storefront/formatter.js'
import { bootValue, direction, language } from './boot.js'

// The storefront's formatter, fed by the boot payload (commera/www/commera.py):
// nothing here reads the browser's locale.
const storeCurrency = bootValue('currency', 'INR')

export const formatter = new Formatter({
  language,
  direction,
  number_format: bootValue('number_format', '#,###.##'),
  store_currency: storeCurrency,
  currency_symbols: bootValue('currency_symbols', {}),
  money_formats: bootValue('money_formats', {}),
  date_formats: bootValue('date_formats', {}),
})

// Dashboard figures are whole units: cents add noise to a list of orders or a stat card.
export const money = (amount) => formatter.money(amount, storeCurrency, 0)

const exactDigits = (amount) => (Number.isInteger(Number(amount ?? 0)) ? 0 : 2)

// A rate band edge such as 499.99 must not round up into the next band's 500.
export const exactMoney = (amount) => formatter.money(amount, storeCurrency, exactDigits(amount))

// For an amount kept in a currency of its own; blank means the site's currency.
export const moneyIn = (amount, currency) => formatter.money(amount, currency || storeCurrency, exactDigits(amount))

// Report figures are read side by side, so they are compacted: 4.8L reads at a glance where
// 4,82,300 has to be counted.
export const compactMoney = (amount) => formatter.compact_money(amount, storeCurrency)

export const count = (value) => formatter.number(value ?? 0)

// A text input's unit prefix: the symbol alone, without the gap a currency code carries.
export const symbolFor = (currency = storeCurrency) => formatter.symbol(currency).trim()

export const formatDate = (value, style = 'medium') => formatter.date(value, style)

// January is 1, as in Frappe's month selects. Gregorian and Latin digits, as formatDate.
export function monthName(month) {
  return new Intl.DateTimeFormat([language, 'en'], {
    month: 'long',
    timeZone: 'UTC',
    calendar: 'gregory',
    numberingSystem: 'latn',
  }).format(new Date(Date.UTC(2000, month - 1, 1)))
}
