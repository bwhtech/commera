import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { money } from './format'

/**
 * The price bands on the store's one Shipping Rule, each naming the delivery option it
 * prices. Bands are in the company currency, which is also the currency `money` formats in.
 */

export const RATE_BASES = [
  { label: 'Order value', value: 'Net Total' },
  { label: 'Weight', value: 'Net Weight' },
]

const available = ref(false)
const rule = ref(null)
const calculateBasedOn = ref('Net Total')
const currency = ref('')
const weightUom = ref('kg')
const bands = ref([])
const deliveryOptions = ref([])

const loadError = ref(null)
const loaded = ref(false)

const { attempt, loading } = createAdminCaller('shipping_rates.')

const isWeightBased = computed(() => calculateBasedOn.value === 'Net Weight')

function apply(data) {
  if (!data) return

  available.value = Boolean(data.available)
  rule.value = data.rule ?? null
  calculateBasedOn.value = data.calculate_based_on ?? 'Net Total'
  currency.value = data.currency ?? ''
  weightUom.value = data.weight_uom ?? 'kg'
  bands.value = data.bands ?? []
  deliveryOptions.value = data.delivery_options ?? []
}

async function load() {
  const { data, error } = await attempt('get_shipping_rates')
  loadError.value = error
  apply(data)
  loaded.value = true
}

async function loadOnce() {
  if (!loaded.value) await load()
}

// The refusal is handed back as well as the screen: the rates editor shows ERPNext's own
// overlap message beside the bands, where the toast alone would vanish before it is read.
async function mutate(method, params = {}) {
  const { data, error } = await attempt(method, params)
  if (data) apply(data)
  return { data, error }
}

// A band row's boundary: money for an order-value rule, the weight unit for a weight rule.
function formatBoundary(value) {
  return isWeightBased.value ? `${Number(value) || 0} ${weightUom.value}` : money(value)
}

function bandsFor(shippingService) {
  return bands.value.filter((band) => (band.shipping_service || null) === shippingService)
}

export function useShippingRates() {
  return {
    available,
    rule,
    calculateBasedOn,
    currency,
    weightUom,
    bands,
    deliveryOptions,
    isWeightBased,
    loadError,
    loaded,
    loading,
    load,
    loadOnce,
    mutate,
    formatBoundary,
    bandsFor,
  }
}

const byFromValue = (first, second) => Number(first.from_value) - Number(second.from_value)

export function formatBandRange(band, formatBoundary = money) {
  const from = Number(band.from_value) || 0
  const to = Number(band.to_value) || 0
  if (!to) return `${formatBoundary(from)} and above`
  return `${formatBoundary(from)}–${formatBoundary(to)}`
}

function formatBand(band, formatBoundary) {
  const price = band.free_shipping ? 'Free' : money(band.shipping_amount)
  const from = Number(band.from_value) || 0
  const to = Number(band.to_value) || 0

  if (!to && !from) return `${price} flat`
  if (!to) return `${price} from ${formatBoundary(from)} and above`
  if (!from) return `${price} up to ${formatBoundary(to)}`
  return `${price} for ${formatBandRange(band, formatBoundary)}`
}

// What bwh_shipping charges when no band covers the cart: the carrier's live quote, then the
// Backup Charge. Null when neither exists, so a cart outside every band is not offered it.
function formatFallback(option) {
  const backupCharge = Number(option?.backup_charge) || 0
  if (option?.service_code && backupCharge) return `carrier rate, ${money(backupCharge)} if unavailable`
  if (option?.service_code) return 'carrier rate'
  if (backupCharge) return money(backupCharge)
  return null
}

/**
 * One line saying what an option costs, from its bands and then its fallback. Empty when
 * nothing prices it at all — the option is then hidden at checkout.
 */
export function rateSummary(bands, option, formatBoundary = money) {
  const bandParts = [...bands].sort(byFromValue).map((band) => formatBand(band, formatBoundary))
  const fallback = formatFallback(option)

  if (!bandParts.length) return fallback ? fallback[0].toUpperCase() + fallback.slice(1) : ''

  // Bands naming no option price no option, so there is no fallback to speak of.
  const coversEverything = bands.some((band) => !Number(band.to_value))
  if (!option || coversEverything) return bandParts.join(' · ')
  return [...bandParts, `${fallback ?? 'hidden at checkout'} otherwise`].join(' · ')
}

export function isPriced(bands, option) {
  return bands.length > 0 || Boolean(formatFallback(option))
}

function bandRange(band) {
  const from = Number(band.from_value) || 0
  // ERPNext checks an open-ended band as the single point at its From value.
  return [from, Number(band.to_value) || from]
}

// ShippingRule.validate_overlapping_shipping_rule_conditions, kept exact so the client refuses
// only what the server would: touching edges (0–999, then 999 up) are allowed.
function rangesOverlap([firstFrom, firstTo], [secondFrom, secondTo]) {
  const separate =
    (firstFrom <= firstTo && firstTo <= secondFrom && secondFrom <= secondTo) ||
    (secondFrom <= secondTo && secondTo <= firstFrom && firstFrom <= firstTo)
  return !separate
}

/**
 * What ShippingRule.validate would refuse across the whole rule, whatever option each band
 * names: a From not below its To, two open-ended bands, or two overlapping ranges.
 * Each conflict is `{ kind: 'order' | 'open' | 'overlap', bands }`.
 */
export function findBandConflicts(bands) {
  const conflicts = []

  for (const band of bands) {
    const to = Number(band.to_value) || 0
    if (to && (Number(band.from_value) || 0) >= to) conflicts.push({ kind: 'order', bands: [band] })
  }

  const openBands = bands.filter((band) => !Number(band.to_value))
  if (openBands.length > 1) conflicts.push({ kind: 'open', bands: openBands })

  bands.forEach((band, index) => {
    for (const other of bands.slice(index + 1)) {
      if (rangesOverlap(bandRange(band), bandRange(other))) {
        conflicts.push({ kind: 'overlap', bands: [band, other] })
      }
    }
  })

  return conflicts
}
