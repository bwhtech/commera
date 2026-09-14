// Shared by the three /analytics/* report screens. The charts stay month-bucketed no matter which
// range is picked — a 7/30-day window just renders one or two bars, which is an honest picture of
// how little data a short window holds rather than switching the chart's x-axis under the reader.
// Mirrors commera.api.admin.analytics.RANGE_MONTHS on the server.
export const RANGE_MONTHS = {
  'Last 7 days': 1,
  'Last 30 days': 1,
  'Last 12 months': 12,
  'All time': 36,
}

export function monthsForRange(range) {
  return RANGE_MONTHS[range] ?? RANGE_MONTHS['Last 12 months']
}

// A report that has never taken an order still answers with a full row per month, every
// figure zero — so `months.length` is 12 and an emptiness check built on it never fires,
// leaving the reader a 0-to-1 axis with a flat line pinned at the bottom. Emptiness on
// these screens means "no value anywhere in the series", not "no rows".
export function hasValues(rows, ...fields) {
  return rows.some((row) => fields.some((field) => Number(row[field]) > 0))
}
