import { __ } from './translation.js'

// Every count the import shows, one whole phrase per string. A row is one variant (one color and
// size); a product with no options has no variants, so it is counted as a product only.

export const productCount = (count) => (count === 1 ? __('1 product') : __('{0} products', [count]))

export const variantCount = (count) => (count === 1 ? __('1 variant') : __('{0} variants', [count]))

export function importLabel({ products, variants }) {
  // Every row skipped: the button is off, and it must not offer to import nothing.
  if (!products) return __('Nothing to import')
  if (!variants) return products === 1 ? __('Import 1 product') : __('Import {0} products', [products])
  if (products === 1) return variants === 1 ? __('Import 1 product (1 variant)') : __('Import 1 product ({0} variants)', [variants])
  return variants === 1
    ? __('Import {0} products (1 variant)', [products])
    : __('Import {0} products ({1} variants)', [products, variants])
}

// The Review step's one-line summary, problems last and only when there are any.
export function reviewSummary({ products, variants, warnings, errors }) {
  // "0 products" says nothing the disabled button and its reason do not already say.
  const parts = products ? [productCount(products)] : []
  if (variants) parts.push(variantCount(variants))
  if (warnings) parts.push(warnings === 1 ? __('1 warning') : __('{0} warnings', [warnings]))
  if (errors) parts.push(errors === 1 ? __('1 row skipped') : __('{0} rows skipped', [errors]))
  return parts
}

export function doneTitle(created, published) {
  if (published === 0) return __('No products were published')
  if (published != null) return published === 1 ? __('1 product is live') : __('{0} products are live', [published])
  if (!created) return __('No products were added')
  return created === 1 ? __('1 product added as a draft') : __('{0} products added as drafts', [created])
}

export const photoCount = (count) => (count === 1 ? __('1 photo') : __('{0} photos', [count]))

// A Review row's original price is struck through only next to a valid price it is above: a blank
// original price reads as 0, and 0 is "above" an invalid -5.
export const showsOriginalPrice = (row) => row.sale_price > 0 && row.compare_at_price > row.sale_price

// The Review filter actually applied: one whose tab is gone (its bucket emptied) falls back to all rows.
export const visibleFilter = (filter, options) => (options.some((option) => option.value === filter) ? filter : 'all')

// Photos are grouped per color of a product, or per product when it has no colors.
export function photoGroupsHavePhoto(withPhoto, total, hasColors) {
  if (total === 1) return hasColors ? __('{0} of 1 color has a photo', [withPhoto]) : __('{0} of 1 product has a photo', [withPhoto])
  return hasColors ? __('{0} of {1} colors have a photo', [withPhoto, total]) : __('{0} of {1} products have a photo', [withPhoto, total])
}

export function photoGroupsNeedPhoto(missing, total, hasColors) {
  if (total === 1) return hasColors ? __('1 color still needs a photo.') : __('1 product still needs a photo.')
  return hasColors
    ? __('{0} of {1} colors still need a photo.', [missing, total])
    : __('{0} of {1} products still need a photo.', [missing, total])
}
