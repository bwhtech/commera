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

// The ERPNext pick step's button. With nothing picked it is off, and it must not offer to import nothing.
export function erpnextImportLabel(selected) {
  if (!selected) return __('Nothing to import')
  return selected === 1 ? __('Import 1 item') : __('Import {0} items', [selected])
}

// The Review step's one-line summary, problems last and only when there are any. A problem carries
// its tone, so the screen can color it the way the row badges are.
export function reviewSummary({ products, variants, warnings, errors }) {
  // "0 products" says nothing the disabled button and its reason do not already say.
  const parts = products ? [{ label: productCount(products) }] : []
  if (variants) parts.push({ label: variantCount(variants) })
  if (warnings) parts.push({ label: warningCount(warnings), tone: 'warning' })
  if (errors) parts.push({ label: skippedRowCount(errors), tone: 'error' })
  return parts
}

export function doneTitle(created, published) {
  if (published === 0) return __('No products were published')
  if (published != null) return published === 1 ? __('1 product is live') : __('{0} products are live', [published])
  if (!created) return __('No products were added')
  return created === 1 ? __('1 product added, not published yet') : __('{0} products added, not published yet', [created])
}

// The line under "… added, not published yet": the title already says it, so this only says what to do.
export function notPublishedBody(created) {
  return created === 1 ? __('Publish it now, or later from its product page.') : __('Publish them now, or later from each product page.')
}

// "Publish all" over one product reads as if there were more.
export const publishAllLabel = (created) => (created === 1 ? __('Publish') : __('Publish all'))

// The line under the result title once Publish all has run.
export function publishedBody(published, notPublished) {
  if (notPublished) {
    return __('{0} could not go live yet. Each one below says what it still needs.', [productCount(notPublished)])
  }
  return published === 1 ? __('Customers can find it on your store now.') : __('Customers can find them on your store now.')
}

export const photoCount = (count) => (count === 1 ? __('1 photo') : __('{0} photos', [count]))

// A Review row's original price is struck through only next to a valid price it is above: a blank
// original price reads as 0, and 0 is "above" an invalid -5.
export const showsOriginalPrice = (row) => row.sale_price > 0 && row.compare_at_price > row.sale_price

// The Review filter actually applied: one whose tab is gone (its bucket emptied) falls back to all rows.
export const visibleFilter = (filter, options) => (options.some((option) => option.value === filter) ? filter : 'all')

// Photos are grouped per color of a product, or per product when it has no colors. A batch can hold
// both, and calling a plain candle a "color" is wrong, so the noun follows what the groups are.
export function photoGroupKind(groups) {
  const colored = groups.filter((group) => group.color).length
  if (!colored) return 'products'
  return colored === groups.length ? 'colors' : 'mixed'
}

// The verb agrees with the count in front of it: "1 of 3 colors has", "2 of 3 colors have".
export function photoGroupsHavePhoto(withPhoto, total, kind) {
  if (total === 1) return kind === 'colors' ? __('{0} of 1 color has a photo', [withPhoto]) : __('{0} of 1 product has a photo', [withPhoto])
  if (withPhoto === 1) {
    if (kind === 'colors') return __('1 of {0} colors has a photo', [total])
    if (kind === 'mixed') return __('1 of {0} products and colors has a photo', [total])
    return __('1 of {0} products has a photo', [total])
  }
  if (kind === 'colors') return __('{0} of {1} colors have a photo', [withPhoto, total])
  if (kind === 'mixed') return __('{0} of {1} products and colors have a photo', [withPhoto, total])
  return __('{0} of {1} products have a photo', [withPhoto, total])
}

export function photoGroupsNeedPhoto(missing, total, kind) {
  if (total === 1) return kind === 'colors' ? __('1 color still needs a photo.') : __('1 product still needs a photo.')
  if (missing === 1) {
    if (kind === 'colors') return __('1 of {0} colors still needs a photo.', [total])
    if (kind === 'mixed') return __('1 of {0} products and colors still needs a photo.', [total])
    return __('1 of {0} products still needs a photo.', [total])
  }
  if (kind === 'colors') return __('{0} of {1} colors still need a photo.', [missing, total])
  if (kind === 'mixed') return __('{0} of {1} products and colors still need a photo.', [missing, total])
  return __('{0} of {1} products still need a photo.', [missing, total])
}

// The Images step's nudge towards adding several photos at once, once there are many to go.
export function manyPhotoGroupsTip(total, kind) {
  if (kind === 'colors') return __('For {0} colors, adding several named photos at once is far quicker.', [total])
  if (kind === 'mixed') return __('For {0} products and colors, adding several named photos at once is far quicker.', [total])
  return __('For {0} products, adding several named photos at once is far quicker.', [total])
}

export const warningCount = (count) => (count === 1 ? __('1 warning') : __('{0} warnings', [count]))

export const skippedRowCount = (count) => (count === 1 ? __('1 row skipped') : __('{0} rows skipped', [count]))

// A run result row, named by its number and the product title it carried. A photo error for a
// product the file never made has no row, only its name.
export function resultRowName({ row, title }) {
  if (!row) return title || ''
  return title ? __('Row {0} · {1}', [row, title]) : __('Row {0}', [row])
}
