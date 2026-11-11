import { computed, ref } from 'vue'
import { toast } from 'frappe-ui'
import { createAdminCaller } from './adminCaller'
import { wasAborted } from './api'
import { errorMessage } from './errors'
import { countryOwners, marketUrls } from './marketUrls'
import { __ } from './translation'

// Module-level, not per panel: the settings sidebar counts the enabled markets before the tab opens.
export const marketActions = createAdminCaller('markets.')

const markets = ref(null)
const choices = ref(null)
const loadError = ref(null)
let queue = Promise.resolve()

const primary = computed(() => markets.value?.find((market) => market.is_primary) ?? null)
const enabledCount = computed(() => (markets.value ?? []).filter((market) => market.enabled).length)

const countryCodes = computed(
  () => new Map((choices.value?.countries ?? []).map((country) => [country.name, country.code.toUpperCase()])),
)
const languageNames = computed(
  () => new Map((choices.value?.languages ?? []).map((language) => [language.code, language.name])),
)
const priceListCurrencies = computed(
  () => new Map((choices.value?.price_lists ?? []).map((priceList) => [priceList.name, priceList.currency])),
)

async function load() {
  const [list, options] = await Promise.all([
    marketActions.attempt('get_markets'),
    marketActions.attempt('get_market_choices'),
  ])
  const error = list.error ?? options.error
  if (wasAborted(error)) return
  loadError.value = error
  if (list.data) markets.value = list.data
  if (options.data) choices.value = options.data
}

function loadOnce() {
  if (!markets.value && !marketActions.loading.value) load()
}

function find(handle) {
  return markets.value?.find((market) => market.handle === handle) ?? null
}

// Replaced in place: the list shows a saved market's answer without a re-read.
function upsert(record) {
  const list = markets.value ?? []
  markets.value = find(record.handle)
    ? list.map((market) => (market.handle === record.handle ? record : market))
    : [...list, record]
}

function drop(handle) {
  markets.value = (markets.value ?? []).filter((market) => market.handle !== handle)
}

// Chained: the caller has one request per method, so two quick switches would abort each other.
function setEnabled(market, isOn) {
  const result = queue.then(async () => {
    const saved = await marketActions.call('update_market', { handle: market.handle, enabled: isOn ? 1 : 0 })
    if (!saved) return
    if (saved.field) {
      toast.error(errorMessage(saved))
      return
    }
    upsert(saved)
    toast.success(
      isOn
        ? __('{0} is open to shoppers', [saved.market_name])
        : __('{0} is off. Shoppers there see the primary market.', [saved.market_name]),
    )
  })
  queue = result.catch(() => {})
  return result
}

function countryCode(country) {
  return countryCodes.value.get(country) ?? ''
}

function languageName(code) {
  return languageNames.value.get(code) ?? code
}

function currencyOf(priceList) {
  return priceListCurrencies.value.get(priceList) ?? ''
}

function urlsOf(market) {
  return marketUrls(market, { defaultLanguage: primary.value?.default_language, countryCode })
}

function ownersExcept(handle) {
  return countryOwners(markets.value ?? [], handle)
}

export const marketStore = {
  markets,
  choices,
  loadError,
  primary,
  enabledCount,
  load,
  loadOnce,
  find,
  upsert,
  drop,
  setEnabled,
  countryCode,
  languageName,
  currencyOf,
  urlsOf,
  ownersExcept,
}
