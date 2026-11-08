import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { wasAborted } from './api'
import { singleFlight } from '../utils/sequence'

/**
 * The store's warehouses and which of them shoppers can collect from.
 *
 * A module-level store rather than a read inside the panel, because the settings sidebar shows how
 * many pickup locations are live before the tab is ever opened — the same reason the payment and
 * shipping counts live in `integrations.js`. Every write answers with the whole screen, which is
 * adopted as-is: the server decides what a warehouse's pickup address is.
 */

const screen = ref(null)
// A refused read leaves `screen` empty, which must not read as "this store has no warehouses".
const loadError = ref(null)
const loaded = ref(false)

const { attempt, call, loading } = createAdminCaller('settings.')

// Frappe answers 1/0, and a Switch handed a number never reads it as its starting state.
const pickupEnabled = computed(() => Boolean(screen.value?.store_pickup_enabled))
const warehouses = computed(() => screen.value?.warehouses ?? [])

// What checkout actually offers: a warehouse allowed for pickup but without an address is skipped
// there, so counting it here would promise a location shoppers never see.
const activeCount = computed(() =>
  pickupEnabled.value
    ? warehouses.value.filter((warehouse) => warehouse.allow_pickup && warehouse.address).length
    : 0,
)

async function load() {
  const { data, error } = await attempt('get_locations')
  // A newer read of the same endpoint aborted this one, and its answer settles the state.
  if (wasAborted(error)) return
  loadError.value = error
  if (data) screen.value = data
  // Only an answer counts as loaded: after a refusal the next open reads again.
  if (data) loaded.value = true
}

// The dialog and the panel both ask on open, so they share one read.
const loadOnce = singleFlight(async () => {
  if (!loaded.value) await load()
})

// Run a write and adopt the screen it returns, or null when the server refused it.
async function mutate(method, params = {}) {
  const data = await call(method, params)
  if (data) screen.value = data
  return data
}

export const pickupLocations = {
  screen,
  loadError,
  loading,
  pickupEnabled,
  warehouses,
  activeCount,
  load,
  loadOnce,
  mutate,
}
