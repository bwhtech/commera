// Client-side state of the first-run onboarding: whether it covers the app, which step is showing,
// and what the owner has typed so far. The server's truth lives in data/onboarding.js.
import { computed, reactive, ref } from 'vue'
import { bootValue, isAdmin } from '../data/boot'
import { __ } from '../data/translation'
import { STEPS, clampStep } from './onboardingSteps'

const STEP_KEY = 'commera:onboarding-step'

// Read from the boot once: finishing flips it here, and no other tab can un-finish it.
export const onboardingOpen = ref(isAdmin && bootValue('onboarding_pending', false))

export function readSavedStep() {
  try {
    return clampStep(Number(localStorage.getItem(STEP_KEY)))
  } catch {
    // Private mode: starting over at the first step is harmless, every field is prefilled.
    return 0
  }
}

function writeSavedStep(index) {
  try {
    if (index) localStorage.setItem(STEP_KEY, String(index))
    else localStorage.removeItem(STEP_KEY)
  } catch {
    /* private mode */
  }
}

export const flow = reactive({
  index: 0,
  // 1 forward, -1 back: the step transition slides the way the owner is going.
  direction: 1,
  // Set by a Continue pressed with a required field empty, so errors never show before a try.
  showErrors: false,
})

export const currentStep = computed(() => STEPS[flow.index])

export function goToStep(index) {
  const next = clampStep(index)
  flow.direction = next >= flow.index ? 1 : -1
  flow.showErrors = false
  flow.index = next
  writeSavedStep(next)
}

export function forgetOnboardingStep() {
  writeSavedStep(0)
}

export function closeOnboarding() {
  forgetOnboardingStep()
  onboardingOpen.value = false
}

export const draft = reactive({
  fullName: '',
  password: '',
  storeName: '',
  storeCategory: '',
  country: '',
  currency: '',
  timeZone: '',
  chartOfAccounts: 'Standard',
  // null leaves the start month to the server's per-country default.
  fiscalYearStartMonth: null,
  // '' leaves the short code to the server, which also steps around one another company holds.
  companyAbbr: '',
  brandLogo: '',
  primaryColor: '',
  theme: '',
  codEnabled: true,
  allowGuestCheckout: true,
})

export function adoptRecord(record) {
  Object.assign(draft, {
    fullName: record.full_name || '',
    storeName: record.store_name || '',
    storeCategory: record.store_category || '',
    country: record.country || '',
    currency: record.currency || '',
    timeZone: record.time_zone || '',
    chartOfAccounts: record.chart_of_accounts || 'Standard',
    fiscalYearStartMonth: record.fiscal_year_start_month || null,
    brandLogo: record.brand_logo || '',
    primaryColor: record.primary_color || '',
    codEnabled: Boolean(record.cod_enabled),
    allowGuestCheckout: Boolean(record.allow_guest_checkout),
  })
}

export const CATEGORIES = [
  { value: 'Fashion', label: __('Fashion'), icon: 'lucide-shirt', hero: __('Wear it well.') },
  { value: 'Beauty', label: __('Beauty'), icon: 'lucide-sparkles', hero: __('Glow, every day.') },
  { value: 'Home', label: __('Home'), icon: 'lucide-sofa', hero: __('Make it home.') },
  { value: 'Food', label: __('Food'), icon: 'lucide-coffee', hero: __('Small batch.') },
  { value: 'Electronics', label: __('Electronics'), icon: 'lucide-headphones', hero: __('Sound, simplified.') },
  { value: 'Other', label: __('Other'), icon: 'lucide-package', hero: __('Made with care.') },
]

// Stand-ins the preview shows faded until the owner has products of their own.
export const SAMPLE_PRODUCTS = {
  Fashion: ['lucide-shirt', 'lucide-shopping-bag', 'lucide-footprints', 'lucide-glasses'],
  Beauty: ['lucide-droplet', 'lucide-sparkles', 'lucide-heart', 'lucide-leaf'],
  Home: ['lucide-coffee', 'lucide-bed', 'lucide-lamp', 'lucide-flower-2'],
  Food: ['lucide-coffee', 'lucide-droplet', 'lucide-package', 'lucide-gift'],
  Electronics: ['lucide-headphones', 'lucide-battery-charging', 'lucide-speaker', 'lucide-usb'],
  Other: ['lucide-star', 'lucide-gift', 'lucide-package', 'lucide-award'],
}

// The owner's choice of brand colour, so these are data, not app styling. Neutral on purpose.
export const BRAND_COLOURS = ['#141414', '#2b4fc4', '#2f6b4f', '#6e2a3a', '#5b45c9', '#6b6b66']

// The preview is a sketch of a storefront, not a render of one: each look is a set of tokens, so
// it holds in dark mode and needs no colour of its own. `dark` scopes frappe-ui's dark tokens to
// the canvas through `data-theme`, which is how a light dashboard shows a dark store.
export const LOOKS = {
  clean: { radius: 'rounded-5', button: 'rounded-full', heading: 'font-sans', hero: 'bg-surface-gray-2', tile: 'bg-surface-gray-2', dark: false },
  editorial: { radius: 'rounded-none', button: 'rounded-none', heading: 'font-serif', hero: 'bg-surface-gray-3', tile: 'bg-surface-gray-1', dark: false },
  market: { radius: 'rounded-3', button: 'rounded-3', heading: 'font-sans', hero: 'bg-surface-gray-3', tile: 'bg-surface-gray-2', dark: false },
  noir: { radius: 'rounded-1', button: 'rounded-full', heading: 'font-sans', hero: 'bg-surface-gray-2', tile: 'bg-surface-gray-2', dark: true },
}

// The themes Commera ships, by name; a theme installed later borrows a look by its place in the list.
const LOOK_BY_THEME = {
  'Summer Theme': 'clean',
  'Commera Starter': 'editorial',
  'Shop Default Theme': 'market',
  'Shop Base Theme': 'noir',
}
const LOOK_ORDER = Object.keys(LOOKS)

export function lookFor(themeName, themeNames = []) {
  const known = LOOK_BY_THEME[themeName]
  if (known) return LOOKS[known]
  const position = Math.max(0, themeNames.indexOf(themeName))
  return LOOKS[LOOK_ORDER[position % LOOK_ORDER.length]]
}
