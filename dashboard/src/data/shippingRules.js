import { ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { money } from './format'

/**
 * The shipping rates a delivery option can price from: ERPNext Shipping Rules and their bands.
 *
 * Kept as a store rather than inside the panel because the delivery option form creates a
 * rule too, and the picker there should see it without a reload. Every mutation answers
 * with the whole screen, the way deliveryOptions.js does.
 */

const rules = ref([])
const defaultAccount = ref('')
const linkOptionsPath = ref('')
// A refused read leaves `rules` empty, which reads as "no rates yet" unless it is kept.
const loadError = ref(null)
const loaded = ref(false)

const { attempt, call, loading } = createAdminCaller('shipping_rules.')

function apply(data) {
  if (!data) return

  rules.value = data.rules ?? []
  defaultAccount.value = data.default_account ?? ''
  linkOptionsPath.value = data.link_options_path ?? ''
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

async function mutate(method, params = {}) {
  const data = await call(method, params)
  if (!data) return null

  apply(data)
  return data
}

function formatBandValue(value, basedOn) {
  return basedOn === 'Net Weight' ? String(value) : money(value)
}

// One line per rule, read in pricing order: "₹99 under ₹999 · Free from ₹999". An open
// top band (no To) is what makes "free above" work, so it reads as "from", never "to 0".
export function describeBands(rule) {
  const basedOn = rule.calculate_based_on
  const line = (rule.bands ?? []).map((band) => {
    const charge = band.shipping_amount ? money(band.shipping_amount) : 'Free'
    const from = formatBandValue(band.from_value, basedOn)
    if (!band.to_value) return `${charge} from ${from}`
    const to = formatBandValue(band.to_value, basedOn)
    if (!band.from_value) return `${charge} up to ${to}`
    return `${charge} for ${from}–${to}`
  })
  return line.join(' · ')
}

export function useShippingRules() {
  return {
    rules,
    defaultAccount,
    linkOptionsPath,
    loadError,
    loading,
    load,
    loadOnce,
    mutate,
  }
}
