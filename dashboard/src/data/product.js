import { computed, unref } from 'vue'

// What a shopper is actually charged for a priced row (a size, or a pricing-screen row): the
// storefront reads the sale price list and only falls back to the default one when there is no
// row there at all — commera/product_detail.py's get_product_detail and commera/api/cart.py's
// get_cart_price both resolve it that way. So the test is "a sale rate exists", never
// "sale_rate < default_rate": the two are equal for the whole life of a discount that has been
// levelled off, and reading that as "no sale" hands back the struck-through price and edits a
// field nobody is charged on.
export function shownPrice(rated) {
  return rated?.sale_rate ?? rated?.default_rate ?? 0
}

// The struck-through reference, which says nothing once it is not above what is charged.
export function compareAtPrice(rated) {
  const compareAt = rated?.default_rate
  return compareAt != null && compareAt > shownPrice(rated) ? compareAt : null
}

export function priceFields(rated) {
  return { price: compareAtPrice(rated), discountedPrice: rated?.sale_rate ?? rated?.default_rate ?? null }
}

export function hasPrice(rate) {
  return rate != null && rate !== '' && Number(rate) > 0
}

export function isPriceValid({ price, discountedPrice }) {
  return !hasPrice(price) || Number(price) > Number(discountedPrice)
}

// An empty Price writes the discounted price to both lists: Item Prices cannot be deleted through
// the API, and equal rates show nothing crossed out.
export function priceRates({ price, discountedPrice }) {
  const charged = Number(discountedPrice)
  return { default_rate: hasPrice(price) ? Number(price) : charged, sale_rate: charged }
}

export const PLACEHOLDER_ATTRIBUTE = 'Title'
export const PLACEHOLDER_OPTION = 'Standard'
export const PLACEHOLDER_SIZE = 'One Size'

export function productOptions(product) {
  const options = [...new Set(product.variants.map((variant) => variant.option))]
  const sizes = [...new Set(product.variants.flatMap((variant) => variant.sizes.map((size) => size.size)))]
  return {
    options: options.filter((option) => option !== PLACEHOLDER_OPTION),
    sizes: sizes.filter((size) => size !== PLACEHOLDER_SIZE),
  }
}

// Everything the product screen needs to summarise a product at a glance,
// derived from catalog.get_product's real shape: a product's sellable units
// are its variants' *sizes* (Color Size Item rows), not the variants
// themselves — a variant (Style Attribute Variant) is one option like a
// colour, and each of its sizes carries its own price and stock.
export function useProductStats(source) {
  return computed(() => {
    const product = unref(source)
    const sizes = product.variants.flatMap((variant) =>
      variant.sizes.map((size) => ({ ...size, variant })),
    )

    const onHand = sizes.reduce((sum, size) => sum + (size.stock ?? 0), 0)
    const committed = sizes.reduce((sum, size) => sum + (size.committed ?? 0), 0)
    // The range a shopper sees, so it reads the charged rate too — a size priced on the sale
    // list alone has no default_rate at all and would otherwise drop out of the range entirely.
    const rates = sizes
      .filter((size) => size.sale_rate != null || size.default_rate != null)
      .map((size) => shownPrice(size))

    const sales = product.recent_sales ?? { units_sold: 0, order_count: 0, revenue: 0 }

    return {
      priceLow: rates.length ? Math.min(...rates) : null,
      priceHigh: rates.length ? Math.max(...rates) : null,
      variantCount: product.variants.length,
      sizeCount: sizes.length,
      onHand,
      committed,
      available: onHand - committed,
      outOfStock: sizes.filter((size) => (size.stock ?? 0) <= 0).length,
      lowStock: sizes.filter((size) => (size.stock ?? 0) > 0 && (size.stock ?? 0) <= 5).length,
      unitsSold: sales.units_sold,
      revenue: sales.revenue,
      orderCount: sales.order_count,
      // Lowest-stock sizes first — the rows a merchant actually needs to act on.
      lowVariants: sizes
        .filter((size) => (size.stock ?? 0) <= 5)
        .sort((a, b) => (a.stock ?? 0) - (b.stock ?? 0))
        .slice(0, 4)
        .map((size) => ({
          id: size.item_code,
          title: `${size.variant.option} · ${size.size}`,
          image: size.variant.images?.[0],
          stock: size.stock,
        })),
    }
  })
}
