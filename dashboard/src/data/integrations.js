import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { getIntegrationLogo, letterPlate } from '../components/integrations/logos'

// The vendor's own colour, and the one place in the app where non-semantic colour is
// correct: it is the thing being recognised. Presentation only — everything else about
// an integration (its fields, whether it is live, what it still needs) comes from the
// server, so adding a provider to a registry in `commera/api/admin/` is enough to make
// it appear here. A provider with no entry still renders, just without its colours.
const BRAND_MARKS = {
  razorpay: { mark: 'R', brand: '#0C2451' },
  stripe: { mark: 'S', brand: '#635BFF' },
  telr: { mark: 'T', brand: '#1A4F9C' },
  tabby: { mark: 'T', brand: '#3BFFC2' },
  shiprocket: { mark: 'S', brand: '#7B2CBF' },
  aftership: { mark: 'A', brand: '#1F2937' },
}

const UNBRANDED = { mark: '•', brand: '#4B5563' }

export function brandFor(slug) {
  const brand = BRAND_MARKS[slug] ?? UNBRANDED
  // A provider the logo registry has never heard of still gets a plate of the same size
  // and shape, carrying its initial on its own colour.
  return { ...brand, plate: getIntegrationLogo(slug) ?? letterPlate(brand.mark, brand.brand) }
}

// One store per registry. Payments and shipping differ only in which two endpoints they
// call: the card shape, the field groups and the save semantics are the same on both
// sides, which is the whole point of the provider-agnostic engine behind them.
export function createIntegrationsStore({ module, listMethod, saveMethod }) {
  const cards = ref([])
  // A refused read leaves `cards` empty, which reads as "this store has no providers"
  // unless the failure is kept.
  const loadError = ref(null)
  const loaded = ref(false)

  const { attempt, call, loading } = createAdminCaller(module)

  const connectedCount = computed(() => cards.value.filter((card) => card.enabled).length)
  const incomplete = computed(() =>
    cards.value.filter((card) => card.enabled && card.missing?.length),
  )

  async function load() {
    const { data, error } = await attempt(listMethod)
    loadError.value = error
    if (data) cards.value = data
    loaded.value = true
  }

  // Loads once per dialog open rather than on every tab switch, but always re-reads after
  // a save, because the server owns `enabled`, `configured` and `missing`.
  async function loadOnce() {
    if (!loaded.value) await load()
  }

  // The server returns the refreshed card, so the list can never drift from what was
  // actually stored — including a refusal to enable a provider whose keys are missing.
  async function save(slug, enabled, values) {
    const card = await call(saveMethod, { slug, enabled: enabled ? 1 : 0, values })
    if (!card) return null

    cards.value = cards.value.map((row) => (row.slug === card.slug ? card : row))
    return card
  }

  return { cards, loadError, loading, connectedCount, incomplete, load, loadOnce, save }
}

export const paymentIntegrations = createIntegrationsStore({
  module: 'payments.',
  listMethod: 'get_payment_integrations',
  saveMethod: 'save_payment_integration',
})

export const shippingIntegrations = createIntegrationsStore({
  module: 'shipping.',
  listMethod: 'get_shipping_integrations',
  saveMethod: 'save_shipping_integration',
})
