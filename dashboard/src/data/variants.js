import { PLACEHOLDER_OPTION, PLACEHOLDER_SIZE } from './product.js'
import { __ } from './translation.js'

// A color (Style Attribute Variant) groups the sellable variants, one per size. Products created with
// sizes only keep a hidden "Standard" color, and products with colors only a hidden "One Size": neither
// is a word the seller chose, so neither is shown. A sizes-only product lists its sizes flat, so its
// hidden color has no label at all.

export function isSizesOnly(variant) {
  return variant.option === PLACEHOLDER_OPTION
}

export function colorLabel(variant) {
  return isSizesOnly(variant) ? '' : variant.option
}

// The scope of one price, said where it is edited: every size shares its color's price. A color with
// no sizes has nothing to share it with, so it gets no hint.
export function priceScopeHint(variant) {
  if (isSizesOnly(variant)) return __('Same price for every size.')
  if (!groupSizes(variant).length) return ''
  return __('Same price for every size of {0}.', [colorLabel(variant)])
}

export function priceUpdatedMessage(variant) {
  return isSizesOnly(variant) ? __('Price updated') : __('Price updated for {0}', [colorLabel(variant)])
}

export function groupSizes(variant) {
  return variant.sizes.filter((size) => size.size !== PLACEHOLDER_SIZE)
}

export function totalStock(variant) {
  return variant.sizes.reduce((sum, size) => sum + (size.stock ?? 0), 0)
}

function sizeTitle(variant, size) {
  if (size.size === PLACEHOLDER_SIZE) return colorLabel(variant)
  if (isSizesOnly(variant)) return size.size
  return `${variant.option} · ${size.size}`
}

// The rows ReceiveStockDialog takes, one per stocked item.
export function stockRows(variants) {
  return variants.flatMap((variant) =>
    variant.sizes
      .filter((size) => size.item_code)
      .map((size) => ({ id: size.item_code, title: sizeTitle(variant, size), onHand: size.stock ?? 0 })),
  )
}
