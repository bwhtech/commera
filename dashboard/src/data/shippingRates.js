import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { exactMoney } from './format'

/**
 * The store company's selling Shipping Rules and the one checkout uses. Bands are on order
 * value, in the company currency, which is also the currency `money` formats in.
 */

const available = ref(false)
const storeRule = ref(null)
const currency = ref('')
const rules = ref([])
const deliveryOptions = ref([])

const loadError = ref(null)
const loaded = ref(false)

const { attempt, loading } = createAdminCaller('shipping_rates.')

// The bands checkout charges: the rule in use, which is what prices each delivery option.
const bands = computed(() => rules.value.find((rule) => rule.name === storeRule.value)?.bands ?? [])

function apply(data) {
  if (!data) return

  available.value = Boolean(data.available)
  storeRule.value = data.store_rule ?? null
  currency.value = data.currency ?? ''
  rules.value = data.rules ?? []
  deliveryOptions.value = data.delivery_options ?? []
}

async function load() {
  const { data, error } = await attempt('get_shipping_rules')
  loadError.value = error
  apply(data)
  loaded.value = true
}

async function loadOnce() {
  if (!loaded.value) await load()
}

// The refusal is handed back as well as the screen: the rule editor shows ERPNext's own
// overlap message beside the bands, where the toast alone would vanish before it is read.
async function mutate(method, params = {}) {
  const { data, error } = await attempt(method, params)
  if (data) apply(data)
  return { data, error }
}

function bandsFor(shippingService) {
  return bands.value.filter((band) => (band.shipping_service || null) === shippingService)
}

export function useShippingRates() {
  return {
    available,
    storeRule,
    currency,
    rules,
    bands,
    deliveryOptions,
    loadError,
    loaded,
    loading,
    load,
    loadOnce,
    mutate,
    bandsFor,
  }
}

const byFromValue = (first, second) => Number(first.from_value) - Number(second.from_value)

export function formatBandRange(band) {
  const from = Number(band.from_value) || 0
  const to = Number(band.to_value) || 0
  if (!to) return `${exactMoney(from)} and above`
  return `${exactMoney(from)}–${exactMoney(to)}`
}

function formatBand(band) {
  const price = band.free_shipping ? 'Free' : exactMoney(band.shipping_amount)
  const from = Number(band.from_value) || 0
  const to = Number(band.to_value) || 0

  if (!to && !from) return `${price} flat`
  if (!to) return `${price} from ${exactMoney(from)} and above`
  if (!from) return `${price} up to ${exactMoney(to)}`
  return `${price} for ${formatBandRange(band)}`
}

// What bwh_shipping charges when no band covers the cart: the carrier's live quote, then the
// Backup Charge. Null when neither exists, so a cart outside every band is not offered it.
function formatFallback(option) {
  const backupCharge = Number(option?.backup_charge) || 0
  if (option?.service_code && backupCharge) return `carrier rate, ${exactMoney(backupCharge)} if unavailable`
  if (option?.service_code) return 'carrier rate'
  if (backupCharge) return exactMoney(backupCharge)
  return null
}

// One line for a rule's row: every band, each naming the delivery option it prices.
export function ruleSummary(bands, optionTitles = {}) {
  return [...bands]
    .sort(byFromValue)
    .map((band) => {
      const price = formatBand(band)
      if (!band.shipping_service) return price
      return `${optionTitles[band.shipping_service] ?? band.shipping_service}: ${price}`
    })
    .join(' · ')
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
 * What ShippingRule.validate would refuse across one rule, whatever option each band names:
 * a From not below its To, two open-ended bands, or two overlapping ranges.
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
