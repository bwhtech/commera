import { __ } from './translation.js'

// Every count the import shows, one whole phrase per string. A row is one variant (one color and
// size); a product with no options has no variants, so it is counted as a product only.

export const productCount = (count) => (count === 1 ? __('1 product') : __('{0} products', [count]))

export const variantCount = (count) => (count === 1 ? __('1 variant') : __('{0} variants', [count]))

export function importLabel({ products, variants }) {
  if (!variants) return products === 1 ? __('Import 1 product') : __('Import {0} products', [products])
  if (products === 1) return variants === 1 ? __('Import 1 product (1 variant)') : __('Import 1 product ({0} variants)', [variants])
  return variants === 1
    ? __('Import {0} products (1 variant)', [products])
    : __('Import {0} products ({1} variants)', [products, variants])
}

// The Review step's one-line summary, problems last and only when there are any.
export function reviewSummary({ products, variants, warnings, errors }) {
  const parts = [productCount(products)]
  if (variants) parts.push(variantCount(variants))
  if (warnings) parts.push(warnings === 1 ? __('1 warning') : __('{0} warnings', [warnings]))
  if (errors) parts.push(errors === 1 ? __('1 row skipped') : __('{0} rows skipped', [errors]))
  return parts
}

export function doneTitle(created, published) {
  if (published != null) return published === 1 ? __('1 product is live') : __('{0} products are live', [published])
  if (!created) return __('No products were added')
  return created === 1 ? __('1 product added as a draft') : __('{0} products added as drafts', [created])
}

export const photoCount = (count) => (count === 1 ? __('1 photo') : __('{0} photos', [count]))
