import { ref, toValue, watch } from 'vue'
import { refDebounced } from '@vueuse/core'
import { createAdminCaller } from './adminCaller'
import { methodUrl, useAdminRead } from './api'
import { moneyIn } from './format'

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

export const discountTypeLabel = (discount) =>
  discountTypeByValue[discount.discount_type]?.label ?? discount.discount_type

export const statusKey = (status) => status.toLowerCase().replaceAll(' ', '_')

export function discountHeading(discount) {
  if (discount.method === 'Automatic') return discount.title || 'Untitled discount'
  if (discount.code) return discount.code
  return discount.generated_codes ? `${discount.generated_codes} unique codes` : discount.title || 'No code yet'
}

export const SCOPE_TARGETS = {
  'Specific Products': { targetType: 'Item', label: 'Products', placeholder: 'Search products' },
  'Specific Collections': { targetType: 'Item Group', label: 'Collections', placeholder: 'Search collections' },
  'Specific Brands': { targetType: 'Brand', label: 'Brands', placeholder: 'Search brands' },
}

export function scopedTargets(discount) {
  const targetType = SCOPE_TARGETS[discount.applies_to]?.targetType
  return discount.targets.filter((row) => row.role !== 'Applies To' || row.target_type === targetType)
}

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
    customers: [],
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
  const money = (value) => moneyIn(value, discount.currency)
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
  const cap = discount.value_type === 'Percentage' && Number(discount.maximum_discount) ? `, up to ${money(discount.maximum_discount)}` : ''
  return `${off(discount.value)} off ${where}${cap}`
}

export function minimumLine(discount) {
  if (discount.minimum_requirement === 'Subtotal') return `Minimum subtotal ${moneyIn(discount.minimum_subtotal, discount.currency)}`
  if (discount.minimum_requirement === 'Quantity') return `Minimum ${discount.minimum_quantity} items`
  return null
}

export function audienceLine(discount) {
  return { 'First Order': 'First order only', 'Customer Groups': 'Chosen customer groups', 'Specific Customers': 'Chosen customers' }[
    discount.eligibility
  ]
}

export function paymentLine(discount) {
  return { Prepaid: 'Prepaid orders only', 'Cash On Delivery': 'Cash on delivery only' }[discount.payment_condition]
}

export function combinationLine(discount) {
  const kinds = [
    discount.combines_with_product && 'product',
    discount.combines_with_order && 'order',
    discount.combines_with_shipping && 'shipping',
  ].filter(Boolean)
  return kinds.length ? `Combines with ${kinds.join(', ')} discounts` : 'Does not combine with other discounts'
}

export function limitLines(discount) {
  return [
    Number(discount.usage_limit) && `${discount.usage_limit} uses in total`,
    discount.once_per_customer && 'Once per customer',
    Number(discount.budget) && `Stops after ${moneyIn(discount.budget, discount.currency)} of discounts`,
  ].filter(Boolean)
}

export function summaryLines(discount) {
  return [
    valueLine(discount),
    minimumLine(discount),
    discount.exclude_sale_items && 'Not on items already on sale',
    audienceLine(discount),
    paymentLine(discount),
    ...limitLines(discount),
    combinationLine(discount),
  ].filter(Boolean)
}

const SEARCH_DEBOUNCE_MS = 300

export function useTargetSearch(targetType, { sellable = false } = {}) {
  const query = ref('')
  const search = refDebounced(query, SEARCH_DEBOUNCE_MS)
  const results = useAdminRead('discounts.search_targets', {
    params: () => ({ target_type: toValue(targetType), search: search.value, sellable: sellable ? 1 : 0 }),
    refetch: true,
  })

  const labels = ref({})
  watch(
    () => results.data,
    (found) => {
      for (const option of found ?? []) labels.value[option.value] = option.label
    },
  )

  function optionsWith(chosen) {
    const found = results.data ?? []
    const shown = new Set(found.map((option) => option.value))
    const missing = chosen.filter((value) => value && !shown.has(value))
    return [...found, ...missing.map((value) => ({ label: labels.value[value] ?? value, value }))]
  }

  return { query, results, labels, optionsWith }
}

const { attempt, call } = createAdminCaller('discounts.')

export const getDiscount = (name) => attempt('get_discount', { name })
export const saveDiscount = (discount) =>
  call('save_discount', { discount: discount.targets ? { ...discount, targets: scopedTargets(discount) } : discount })
export const deleteDiscount = (name) => call('delete_discount', { name })
export const createCodes = (name, count, prefix) => call('create_codes', { name, count, prefix })
export const getEditorOptions = () => call('get_editor_options')

export function codesDownloadUrl(name) {
  return `${methodUrl('discounts.download_codes')}?name=${encodeURIComponent(name)}`
}
