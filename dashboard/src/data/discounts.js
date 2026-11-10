import { ref, toValue, watch } from 'vue'
import { refDebounced } from '@vueuse/core'
import { createAdminCaller } from './adminCaller'
import { methodUrl, useAdminRead } from './api'
import { moneyIn } from './format'
import { __ } from './translation'

export const DISCOUNT_TYPES = [
  {
    slug: 'products',
    value: 'Amount Off Products',
    label: __('Amount off products'),
    icon: 'lucide-tag',
    description: __('A percentage or amount off chosen products, collections or brands.'),
  },
  {
    slug: 'order',
    value: 'Amount Off Order',
    label: __('Amount off order'),
    icon: 'lucide-shopping-cart',
    description: __('Off the order subtotal, with optional spend tiers and a cap.'),
  },
  {
    slug: 'buy-x-get-y',
    value: 'Buy X Get Y',
    label: __('Buy X get Y'),
    icon: 'lucide-gift',
    description: __('Buy a quantity or amount of some products, get others free or cheaper.'),
  },
  {
    slug: 'shipping',
    value: 'Free Shipping',
    label: __('Free shipping'),
    icon: 'lucide-truck',
    description: __('Free or cheaper delivery above a spend, on chosen delivery options.'),
  },
]

export const discountTypeByValue = Object.fromEntries(DISCOUNT_TYPES.map((type) => [type.value, type]))
export const discountTypeBySlug = Object.fromEntries(DISCOUNT_TYPES.map((type) => [type.slug, type]))

export const discountTypeLabel = (discount) =>
  discountTypeByValue[discount.discount_type]?.label ?? discount.discount_type

export const statusKey = (status) => status.toLowerCase().replaceAll(' ', '_')

export function discountHeading(discount) {
  if (discount.method === 'Automatic') return discount.title || __('Untitled discount')
  if (discount.code) return discount.code
  return discount.generated_codes ? __('{0} unique codes', [discount.generated_codes]) : discount.title || __('No code yet')
}

export const SCOPE_TARGETS = {
  'Specific Products': { targetType: 'Item', label: __('Products'), placeholder: __('Search products') },
  'Specific Collections': { targetType: 'Item Group', label: __('Collections'), placeholder: __('Search collections') },
  'Specific Brands': { targetType: 'Brand', label: __('Brands'), placeholder: __('Search brands') },
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
  if (discount.discount_type === 'Buy X Get Y') return buyXGetYLine(discount, money)
  if (discount.discount_type === 'Free Shipping') {
    return discount.shipping_percentage >= 100 ? __('Free delivery') : __('{0}% off delivery', [discount.shipping_percentage])
  }
  if (discount.tiered && discount.tiers?.length) {
    return discount.tiers.map((tier) => __('{0}+ gets {1}', [money(tier.minimum_subtotal), off(tier.value)])).join(' · ')
  }
  const onOrder = discount.discount_type === 'Amount Off Order'
  const value = off(discount.value)
  if (discount.value_type === 'Percentage' && Number(discount.maximum_discount)) {
    const cap = money(discount.maximum_discount)
    return onOrder ? __('{0} off the order, up to {1}', [value, cap]) : __('{0} off products, up to {1}', [value, cap])
  }
  return onOrder ? __('{0} off the order', [value]) : __('{0} off products', [value])
}

function buyXGetYLine(discount, money) {
  const buy = discount.buy_requirement === 'Quantity' ? discount.buy_value : money(discount.buy_value)
  const get = discount.get_quantity
  if (discount.get_value_type === 'Free') return __('Buy {0}, get {1} free', [buy, get])
  if (discount.get_value_type === 'Percentage') return __('Buy {0}, get {1} {2}% off', [buy, get, discount.get_value])
  return __('Buy {0}, get {1} {2} off each', [buy, get, money(discount.get_value)])
}

export function minimumLine(discount) {
  if (discount.minimum_requirement === 'Subtotal') return __('Minimum subtotal {0}', [moneyIn(discount.minimum_subtotal, discount.currency)])
  if (discount.minimum_requirement === 'Quantity') return __('Minimum {0} items', [discount.minimum_quantity])
  return null
}

export function audienceLine(discount) {
  return { 'First Order': __('First order only'), 'Customer Groups': __('Chosen customer groups'), 'Specific Customers': __('Chosen customers') }[
    discount.eligibility
  ]
}

export function paymentLine(discount) {
  return { Prepaid: __('Prepaid orders only'), 'Cash On Delivery': __('Cash on delivery only') }[discount.payment_condition]
}

export function combinationLine(discount) {
  const kinds = [
    discount.combines_with_product && __('product'),
    discount.combines_with_order && __('order'),
    discount.combines_with_shipping && __('shipping'),
  ].filter(Boolean)
  return kinds.length ? __('Combines with {0} discounts', [kinds.join(', ')]) : __('Does not combine with other discounts')
}

export function limitLines(discount) {
  return [
    Number(discount.usage_limit) && __('{0} uses in total', [discount.usage_limit]),
    discount.once_per_customer && __('Once per customer'),
    Number(discount.budget) && __('Stops after {0} of discounts', [moneyIn(discount.budget, discount.currency)]),
  ].filter(Boolean)
}

export function summaryLines(discount) {
  return [
    valueLine(discount),
    minimumLine(discount),
    discount.exclude_sale_items && __('Not on items already on sale'),
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
// delete_discount answers nothing, so success is the absence of an error, not a truthy answer.
export const deleteDiscount = async (name) => !(await attempt('delete_discount', { name })).error
export const createCodes = (name, count, prefix) => call('create_codes', { name, count, prefix })
export const getEditorOptions = () => call('get_editor_options')

export function codesDownloadUrl(name) {
  return `${methodUrl('discounts.download_codes')}?name=${encodeURIComponent(name)}`
}
