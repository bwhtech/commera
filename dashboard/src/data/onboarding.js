// First-run onboarding: what the owner already told Frappe Cloud, the background store setup, and
// the writes each step settles with. All of it is commera.api.admin.onboarding.
import { reactive, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { useAdminRead } from './api'
import { setupPollDelay } from '../ia/onboardingSteps'

const { attempt } = createAdminCaller('onboarding.')

// The reads are GET-only on the server, and createAdminCaller only POSTs.
const onboardingRequest = useAdminRead('onboarding.get_onboarding', { immediate: false })
// Quiet: a poll that misses one beat would otherwise toast every two seconds.
const statusRequest = useAdminRead('onboarding.get_setup_status', { immediate: false, quiet: true })
const productsRequest = useAdminRead('catalog.get_products', {
  immediate: false,
  quiet: true,
  params: { page_length: 4 },
})
// useCall's fetch() takes no arguments, so the country rides a params function.
const defaultsCountry = ref('')
const countryDefaultsRequest = useAdminRead('onboarding.get_country_defaults', {
  immediate: false,
  quiet: true,
  params: () => ({ country: defaultsCountry.value }),
})

export const onboarding = ref(null)
export const onboardingLoadError = ref(null)

// One owner for the setup state: the header badge, the products step and the finish button all
// read this, and only adoptSetup() writes it. `status` is the server's (idle, running, done,
// failed); `poll` is ours: whether this tab is still asking (`polling`), gave up asking
// (`stalled`), or has nothing to ask about (`off`).
export const storeSetup = reactive({ status: 'idle', error: '', poll: 'off' })

// No socket is open in the dashboard, so the job's realtime event cannot reach it; polling is
// the one channel, on the schedule setupPollDelay() sets. Once it says stop, the tab says so
// rather than polling a job that died with its worker for as long as the tab stays open.
let pollTimer = null
let pollStartedAt = 0

function adoptSetup(answer) {
  if (!answer) return
  storeSetup.status = answer.status
  storeSetup.error = answer.error || ''
  if (answer.status === 'running') schedulePoll()
  else stopSetupPolling()
}

function schedulePoll() {
  if (pollTimer) return
  if (storeSetup.poll !== 'polling') {
    storeSetup.poll = 'polling'
    pollStartedAt = Date.now()
  }
  const delay = setupPollDelay(Date.now() - pollStartedAt)
  if (delay === null) {
    storeSetup.poll = 'stalled'
    return
  }
  pollTimer = setTimeout(async () => {
    pollTimer = null
    const answer = await statusRequest.fetch()
    // Stopped while this was in flight: the flow closed, or a newer answer already settled it.
    if (storeSetup.poll !== 'polling') return
    if (answer) adoptSetup(answer)
    else if (storeSetup.status === 'running') schedulePoll()
  }, delay)
}

export function stopSetupPolling() {
  clearTimeout(pollTimer)
  pollTimer = null
  storeSetup.poll = 'off'
}

// "Check again" after a stall: a fresh window of polling, starting now.
export function resumeSetupPolling() {
  stopSetupPolling()
  if (storeSetup.status === 'running') schedulePoll()
}

export async function loadOnboarding() {
  const data = await onboardingRequest.fetch()
  onboardingLoadError.value = onboardingRequest.error
  if (!data) return null
  onboarding.value = data
  adoptSetup(data.setup)
  return data
}

// Each write resolves true once it landed; a refusal has already toasted in useAdminAction.
async function write(method, params) {
  const { data, error } = await attempt(method, params)
  return error ? null : data ?? {}
}

export async function saveProfile({ fullName, password }) {
  return Boolean(await write('save_profile', { full_name: fullName.trim(), password: password || undefined }))
}

export async function startStoreSetup(values) {
  const answer = await write('start_store_setup', values)
  adoptSetup(answer)
  return Boolean(answer)
}

export async function saveBrand({ brandLogo, primaryColor }) {
  return Boolean(await write('save_brand', { brand_logo: brandLogo, primary_color: primaryColor }))
}

export async function saveSelling({ codEnabled, allowGuestCheckout }) {
  return Boolean(
    await write('save_selling', { cod_enabled: codEnabled ? 1 : 0, allow_guest_checkout: allowGuestCheckout ? 1 : 0 }),
  )
}

export async function completeOnboarding() {
  return Boolean(await write('complete_onboarding'))
}

// The first few products the owner made during onboarding, for the store preview.
export const storeProducts = ref([])

export async function loadStoreProducts() {
  const data = await productsRequest.fetch()
  if (data) storeProducts.value = (data.products ?? []).filter((product) => !product.disabled)
}

// `{ currency, timeZone, fiscalYearStartMonth, chartsOfAccounts }` for a country, or null on a refusal.
export async function getCountryDefaults(country) {
  defaultsCountry.value = country
  const data = await countryDefaultsRequest.fetch()
  if (!data) return null
  return {
    currency: data.currency,
    timeZone: data.time_zone,
    fiscalYearStartMonth: data.fiscal_year_start_month,
    chartsOfAccounts: data.charts_of_accounts ?? [],
  }
}
