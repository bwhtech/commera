import { dayjs } from 'frappe-ui'
import { bootValue } from './boot'
import { money } from './formatter'
import { __ } from './translation'

export { compactMoney, count, exactMoney, formatDate, money, moneyIn, monthName, symbolFor } from './formatter'

export const discountMoney = (n, format = money) => `−${format(n)}`

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
  missing: __('Missing'),
  outdated: __('Outdated'),
  unsaved: __('Unsaved'),
  paid: __('Paid'),
  pending: __('Payment pending'),
  refunded: __('Refunded'),
  partially_refunded: __('Partly refunded'),
  unfulfilled: __('Unfulfilled'),
  fulfilled: __('Fulfilled'),
  partial: __('Partly fulfilled'),
  delivered: __('Delivered'),
  cancelled: __('Cancelled'),
  active: __('Active'),
  draft: __('Draft'),
  archived: __('Archived'),
  published: __('Published'),
  sent: __('Sent'),
  queued: __('Queued'),
  sending: __('Sending'),
  retrying: __('Retrying'),
  failed: __('Failed'),
  scheduled: __('Scheduled'),
  expired: __('Expired'),
  used_up: __('Used up'),
  disabled: __('Disabled'),
}

export const label = (key) => LABELS[key] ?? key

// One lookup for every status pill in the app — colour only where it encodes state.
const THEMES = {
  missing: 'red',
  outdated: 'amber',
  unsaved: 'blue',
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
  if (low == null && high == null) return __('No price')
  if (low === high) return money(low)
  return `${money(low)} – ${money(high)}`
}

export function stockTone(qty) {
  if (qty <= 0) return 'text-ink-red-6'
  if (qty <= 5) return 'text-ink-amber-7'
  return 'text-ink-gray-7'
}
