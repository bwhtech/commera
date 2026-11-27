import { PLACEHOLDER_OPTION, PLACEHOLDER_SIZE } from './product.js'
import { __ } from './translation.js'

// A color (Style Attribute Variant) groups the sellable variants, one per size. Products created with
// sizes only keep a hidden "Standard" color, and products with colors only a hidden "One Size": neither
// is a word the seller chose, so neither is shown.

export function colorLabel(variant) {
  return variant.option === PLACEHOLDER_OPTION ? __('All sizes') : variant.option
}

export function groupSizes(variant) {
  return variant.sizes.filter((size) => size.size !== PLACEHOLDER_SIZE)
}

export function totalStock(variant) {
  return variant.sizes.reduce((sum, size) => sum + (size.stock ?? 0), 0)
}

function sizeTitle(variant, size) {
  if (size.size === PLACEHOLDER_SIZE) return colorLabel(variant)
  if (variant.option === PLACEHOLDER_OPTION) return size.size
  return `${variant.option} · ${size.size}`
}

// The rows ReceiveStockDialog takes, one per stocked item.
export function stockRows(variants) {
  return variants.flatMap((variant) =>
    variant.sizes
      .filter((size) => size.item_code)
      .map((size) => ({ id: size.item_code, title: sizeTitle(variant, size), sku: size.item_code, onHand: size.stock ?? 0 })),
  )
}
