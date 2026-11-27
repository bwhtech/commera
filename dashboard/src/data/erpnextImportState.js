import { __ } from './translation.js'

export const KIND_LABELS = {
  plain: __('No options'),
  colour_size: __('Color and size'),
  size_only: __('Size only'),
  colour_only: __('Color only'),
  other_attributes: __('Other options'),
}

export function preselectedCodes(items) {
  return items.filter((item) => item.preselected).map((item) => item.item_code)
}

export function selectionOnPage(items, selected) {
  return items.map((item) => item.item_code).filter((itemCode) => selected.includes(itemCode))
}

export function selectedAfter(items, pageSelection, selected) {
  const pageCodes = new Set(items.map((item) => item.item_code))
  return [...selected.filter((itemCode) => !pageCodes.has(itemCode)), ...pageSelection]
}

export function itemCodesToImport(selected, importableCount) {
  return selected.length === importableCount ? null : selected
}

export const isRunSettled = (status) => status === 'done' || status === 'failed'

export function runPercent(status) {
  if (!status?.total) return 0
  return Math.min(100, Math.round((status.done / status.total) * 100))
}
