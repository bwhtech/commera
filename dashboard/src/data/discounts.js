import { createAdminCaller } from './adminCaller'
import { money } from './format'

// The route slug is what a new-discount URL carries; the label is what the server stores.
export const DISCOUNT_TYPES = [
  {
    slug: 'products',
    value: 'Amount Off Products',
    label: 'Amount off products',
    icon: 'lucide-tag',
    description: 'A percentage or amount off chosen products, collections or brands.',
  },
  {
    slug: 'order',
    value: 'Amount Off Order',
    label: 'Amount off order',
    icon: 'lucide-shopping-cart',
    description: 'Off the order subtotal, with optional spend tiers and a cap.',
  },
  {
    slug: 'buy-x-get-y',
    value: 'Buy X Get Y',
    label: 'Buy X get Y',
    icon: 'lucide-gift',
    description: 'Buy a quantity or amount of some products, get others free or cheaper.',
  },
  {
    slug: 'shipping',
    value: 'Free Shipping',
    label: 'Free shipping',
    icon: 'lucide-truck',
    description: 'Free or cheaper delivery above a spend, on chosen delivery options.',
  },
]

export const discountTypeByValue = Object.fromEntries(DISCOUNT_TYPES.map((type) => [type.value, type]))
export const discountTypeBySlug = Object.fromEntries(DISCOUNT_TYPES.map((type) => [type.slug, type]))

export const STATUS_THEMES = { Active: 'green', Scheduled: 'blue', Expired: 'gray', 'Used Up': 'amber', Disabled: 'gray' }

export function blankDiscount(discountType, currency) {
  return {
    name: null,
    title: '',
    code: '',
    method: 'Code',
    discount_type: discountType,
    enabled: 1,
    starts_on: new Date().toISOString().slice(0, 10),
    ends_on: null,
    value_type: 'Percentage',
    value: 10,
    maximum_discount: 0,
    fixed_applies_to: 'Each Item',
    currency,
    tiered: 0,
    tiers: [],
    applies_to: 'All Products',
    exclude_sale_items: 0,
    targets: [],
    buy_requirement: 'Quantity',
    buy_value: 2,
    uses_per_order: 0,
    get_quantity: 1,
    get_value_type: 'Free',
    get_value: 0,
    delivery_options: '',
    shipping_percentage: 100,
    maximum_shipping_rate: 0,
    minimum_requirement: discountType === 'Free Shipping' ? 'Subtotal' : 'None',
    minimum_subtotal: 0,
    minimum_quantity: 0,
    payment_condition: 'Any',
    eligibility: 'Everyone',
    customer_groups: [],
    // A free-shipping offer is meant to sit beside the store's other discounts.
    combines_with_product: discountType === 'Free Shipping' ? 1 : 0,
    combines_with_order: discountType === 'Free Shipping' ? 1 : 0,
    combines_with_shipping: 1,
    usage_limit: 0,
    once_per_customer: 0,
    budget: 0,
    campaign: null,
    discount_account: null,
    generated_codes: 0,
    generated_codes_used: 0,
    performance: null,
  }
}

function valueLine(discount) {
  const off = (value) => (discount.value_type === 'Percentage' ? `${value}%` : money(value))
  if (discount.discount_type === 'Buy X Get Y') {
    const reward = { Free: 'free', Percentage: `${discount.get_value}% off` }[discount.get_value_type] ?? `${money(discount.get_value)} off each`
    const buy = discount.buy_requirement === 'Quantity' ? discount.buy_value : money(discount.buy_value)
    return `Buy ${buy}, get ${discount.get_quantity} ${reward}`
  }
  if (discount.discount_type === 'Free Shipping') {
    return discount.shipping_percentage >= 100 ? 'Free delivery' : `${discount.shipping_percentage}% off delivery`
  }
  if (discount.tiered && discount.tiers?.length) {
    return discount.tiers.map((tier) => `${money(tier.minimum_subtotal)}+ gets ${off(tier.value)}`).join(' · ')
  }
  const where = discount.discount_type === 'Amount Off Order' ? 'the order' : 'products'
  const cap = discount.value_type === 'Percentage' && discount.maximum_discount ? `, up to ${money(discount.maximum_discount)}` : ''
  return `${off(discount.value)} off ${where}${cap}`
}

// One sentence per rule, in the order a shopper meets them. The list shows the first few,
// the editor's summary shows them all.
export function summaryLines(discount) {
  const combines = [
    discount.combines_with_product && 'product',
    discount.combines_with_order && 'order',
    discount.combines_with_shipping && 'shipping',
  ].filter(Boolean)
  return [
    valueLine(discount),
    discount.minimum_requirement === 'Subtotal' && `Minimum subtotal ${money(discount.minimum_subtotal)}`,
    discount.minimum_requirement === 'Quantity' && `Minimum ${discount.minimum_quantity} items`,
    discount.exclude_sale_items && 'Not on items already on sale',
    { 'First Order': 'First order only', 'Customer Groups': 'Chosen customer groups' }[discount.eligibility],
    { Prepaid: 'Prepaid orders only', 'Cash On Delivery': 'Cash on delivery only' }[discount.payment_condition],
    discount.once_per_customer && 'Once per customer',
    discount.usage_limit && `${discount.usage_limit} uses in total`,
    discount.budget && `Stops after ${money(discount.budget)} of discounts`,
    combines.length ? `Combines with ${combines.join(', ')} discounts` : 'Does not combine with other discounts',
  ].filter(Boolean)
}

const { attempt, call } = createAdminCaller('discounts.')

export const getDiscount = (name) => attempt('get_discount', { name })
export const saveDiscount = (discount) => call('save_discount', { discount })
export const deleteDiscount = (name) => attempt('delete_discount', { name })
export const createCodes = (name, count, prefix) => call('create_codes', { name, count, prefix })
export const testDiscount = (discount, lines, paymentKind, firstOrder, customer) =>
  call('test_discount', { discount, lines, payment_kind: paymentKind, first_order: firstOrder ? 1 : 0, customer })
export const getEditorOptions = () => call('get_editor_options')
export const searchTargets = (targetType, search, sellable = false) =>
  call('search_targets', { target_type: targetType, search, sellable: sellable ? 1 : 0 })

export function codesDownloadUrl(name) {
  return `/api/v2/method/commera.api.admin.discounts.download_codes?name=${encodeURIComponent(name)}`
}
