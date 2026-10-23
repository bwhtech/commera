import { dayjs } from 'frappe-ui'
import { bootValue } from './boot'

// The shell (commera/www/commera.py) drops the site's reporting currency and
// its symbol on `window`, so money reads correctly without any screen
// threading a symbol down from its own endpoint — see boot.js.
const currencyCode = bootValue('currency', 'INR')
const currencySymbol = bootValue('currency_symbol', '')

function moneyFormatter(compact, maximumFractionDigits = compact ? 1 : 0, currency = currencyCode) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits,
  })
}

// Intl has no narrow symbol for some currencies (AED, SAR…) in a Latin locale
// and prints the code instead, so the site's own symbol is swapped in.
function formatWithSymbol(amount, formatter, symbol = currencySymbol) {
  const value = amount ?? 0
  if (!symbol) return formatter.format(value)
  return formatter
    .formatToParts(value)
    .map((part) => (part.type === 'currency' ? symbol : part.value))
    .join('')
}

// The site's own symbol for its currency; Intl's narrow symbol for any other, or when the
// shell did not boot one (the Vite dev server serves a bare index.html).
export function symbolFor(code = currencyCode) {
  if (code === currencyCode && currencySymbol) return currencySymbol
  const currencyPart = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: code,
    currencyDisplay: 'narrowSymbol',
  })
    .formatToParts(0)
    .find((part) => part.type === 'currency')
  return currencyPart?.value ?? code
}

export const money = (n) => formatWithSymbol(n, moneyFormatter(false))

const exactDigits = (n) => (Number.isInteger(Number(n ?? 0)) ? 0 : 2)

// A rate band edge such as 499.99 must not round up into the next band's ₹500.
export const exactMoney = (n) => formatWithSymbol(n, moneyFormatter(false, exactDigits(n)))

// For an amount kept in a currency of its own; blank means the site's currency.
export function moneyIn(n, currency) {
  const code = currency || currencyCode
  return formatWithSymbol(n, moneyFormatter(false, exactDigits(n), code), symbolFor(code))
}

export const discountMoney = (n, format = money) => `−${format(n)}`

// Report figures are read side by side, so they are compacted: ₹4.8L reads at
// a glance where ₹4,82,300 has to be counted.
export const compactMoney = (n) => formatWithSymbol(n, moneyFormatter(true))

/**
 * Frappe writes its formats in lowercase tokens (dd-mm-yyyy, HH:mm:ss); dayjs
 * wants the date parts uppercased. Month stays `MM` in both, so only the day
 * and year tokens need lifting.
 */
function toDayjsPattern(frappeFormat) {
  return frappeFormat
    .replace(/yyyy/g, 'YYYY')
    .replace(/yy(?!YY)/g, 'YY')
    .replace(/dd/g, 'DD')
    .replace(/mm/g, 'MM')
}

const dateFormat = toDayjsPattern(bootValue('date_format', 'yyyy-mm-dd'))
// The list-row form drops the year (and whatever separator sits next to it) —
// derived from the site's own format rather than a second hardcoded pattern.
const shortDateFormat = dateFormat.replace(/[-/,.\s]*YYYY[-/,.\s]*/, '').trim() || dateFormat

export const shortDate = (iso) => (iso ? dayjs(iso).format(shortDateFormat) : '—')

export const longDate = (iso) => (iso ? dayjs(iso).format(dateFormat) : '—')

const LABELS = {
  paid: 'Paid',
  pending: 'Payment pending',
  refunded: 'Refunded',
  partially_refunded: 'Partly refunded',
  unfulfilled: 'Unfulfilled',
  fulfilled: 'Fulfilled',
  partial: 'Partly fulfilled',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  active: 'Active',
  draft: 'Draft',
  archived: 'Archived',
  published: 'Published',
  sent: 'Sent',
  queued: 'Queued',
  sending: 'Sending',
  retrying: 'Retrying',
  failed: 'Failed',
  scheduled: 'Scheduled',
  expired: 'Expired',
  used_up: 'Used up',
  disabled: 'Disabled',
}

export const label = (key) => LABELS[key] ?? key

// One lookup for every status pill in the app — colour only where it encodes state.
const THEMES = {
  paid: 'green',
  delivered: 'green',
  fulfilled: 'green',
  active: 'green',
  published: 'green',
  sent: 'green',
  pending: 'amber',
  partial: 'amber',
  partially_refunded: 'amber',
  to_fulfil: 'amber',
  delivery_note_drafted: 'amber',
  packed: 'amber',
  partly_fulfilled: 'amber',
  shipped: 'blue',
  scheduled: 'blue',
  used_up: 'amber',
  unfulfilled: 'red',
  cancelled: 'red',
  failed: 'red',
  refunded: 'gray',
  draft: 'gray',
  archived: 'gray',
  confirmation_pending: 'gray',
  expired: 'gray',
  disabled: 'gray',
  returned: 'gray',
}

export const statusTheme = (key) => THEMES[key] ?? 'gray'

// A product's sellable units rarely share one price — this is the one place
// that decides how a low/high pair reads, so every screen with a price range
// agrees on it.
export function priceRange(low, high) {
  if (low == null && high == null) return 'No price'
  if (low === high) return money(low)
  return `${money(low)} – ${money(high)}`
}

export function stockTone(qty) {
  if (qty <= 0) return 'text-ink-red-6'
  if (qty <= 5) return 'text-ink-amber-7'
  return 'text-ink-gray-7'
}
