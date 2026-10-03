import { dayjs } from 'frappe-ui'
import { bootValue } from './boot'

// The shell (commera/www/commera.py) drops the site's reporting currency and
// its symbol on `window`, so money reads correctly without any screen
// threading a symbol down from its own endpoint — see boot.js.
const currencyCode = bootValue('currency', 'INR')
const currencySymbol = bootValue('currency_symbol', '')

function moneyFormatter(compact) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: currencyCode,
    currencyDisplay: 'narrowSymbol',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  })
}

// Intl has no narrow symbol for some currencies (AED, SAR…) in a Latin locale
// and prints the code instead, so the site's own symbol is swapped in.
function formatWithSymbol(amount, formatter) {
  const value = amount ?? 0
  if (!currencySymbol) return formatter.format(value)
  return formatter
    .formatToParts(value)
    .map((part) => (part.type === 'currency' ? currencySymbol : part.value))
    .join('')
}

export const money = (n) => formatWithSymbol(n, moneyFormatter(false))

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
  pending: 'orange',
  partial: 'orange',
  partially_refunded: 'orange',
  to_fulfil: 'orange',
  delivery_note_drafted: 'orange',
  packed: 'orange',
  partly_fulfilled: 'orange',
  shipped: 'blue',
  unfulfilled: 'red',
  cancelled: 'red',
  failed: 'red',
  refunded: 'gray',
  draft: 'gray',
  archived: 'gray',
  confirmation_pending: 'gray',
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
