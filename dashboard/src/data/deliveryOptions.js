import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'

/**
 * The delivery options a shopper picks between at checkout.
 *
 * A sibling of the carrier registry, not a copy of it: a carrier is a connection with
 * keys, a delivery option is a line on the checkout page with a price. The server owns
 * every rule about both — which is why each mutation here answers with the whole screen
 * and this store adopts it, the way theme.js does, rather than patching a row by hand.
 */

const options = ref([])
// The edit form's fields come from the doctype's own meta, in Desk layout order — so a
// docfield added to the shipping service shows up here with no change to this app.
const fieldGroups = ref([])
const importProviders = ref([])
// The endpoint that searches this doctype's Link fields, when the server offers one. It is
// asked for rather than assumed: a picker pointed at a method that does not exist toasts a
// failure the moment the form opens, where a plain box just asks for the name.
const linkOptionsPath = ref('')

// A refused read leaves `options` empty, which reads as "this store has no delivery
// options" unless the failure is kept.
const loadError = ref(null)
const loaded = ref(false)

const { attempt, call, loading } = createAdminCaller('delivery_options.')

const enabledCount = computed(() => options.value.filter((option) => option.enabled).length)

function apply(data) {
  if (!data) return

  options.value = data.options ?? []
  fieldGroups.value = data.field_groups ?? []
  importProviders.value = data.import_providers ?? []
  linkOptionsPath.value = data.link_options_path ?? ''
}

async function load() {
  const { data, error } = await attempt('get_delivery_options')
  loadError.value = error
  apply(data)
  loaded.value = true
}

// Loads once per dialog open rather than on every tab switch. Every mutation re-reads
// anyway, because the answer to one is the refreshed screen.
async function loadOnce() {
  if (!loaded.value) await load()
}

// Run a mutation and adopt the screen it returns, or null when the server refused it.
async function mutate(method, params = {}) {
  const data = await call(method, params)
  if (!data) return null

  apply(data)
  return data
}

// The only endpoint here that answers with something other than the whole screen: the
// services one carrier sells, asked for when the import dialog opens. Nothing is stored,
// because what a carrier offers is not state this store owns.
async function carrierServices(provider) {
  return await call('get_carrier_service_choices', { provider })
}

export function useDeliveryOptions() {
  return {
    options,
    fieldGroups,
    importProviders,
    linkOptionsPath,
    enabledCount,
    loadError,
    loaded,
    loading,
    load,
    loadOnce,
    mutate,
    carrierServices,
  }
}
