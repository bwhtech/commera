// The onboarding flow's shape. Every import keeps its `.js` so tests/unit can load it under plain node.
import { __ } from '../data/translation.js'

// `focus` names the area of the store preview a step outlines; `optional` offers Skip.
export const STEPS = [
  { key: 'you', title: __('Welcome') },
  { key: 'store', title: __('Your store'), focus: 'brand' },
  { key: 'done', title: '' },
]

export const STEP_INDEX = Object.fromEntries(STEPS.map((step, index) => [step.key, index]))

export function clampStep(index) {
  return Math.min(STEPS.length - 1, Math.max(0, Number.isInteger(index) ? index : 0))
}

const LEGACY_STEP_KEYS = ['you', 'store', 'brand', 'theme', 'selling', 'products', 'done']
const RETIRED_STEP_KEYS = ['brand', 'theme', 'selling', 'products']

// The step a reload resumes at. Every step after the store needs the store setup to have been
// started; a setup that never started (or a cache that forgot it) sends the owner back to start it.
export function resumeStep(saved, setupStatus) {
  const key = /^\d+$/.test(String(saved ?? '')) ? LEGACY_STEP_KEYS[Number(saved)] : saved
  const index = RETIRED_STEP_KEYS.includes(key)
    ? STEP_INDEX[setupStatus === 'done' ? 'done' : 'store']
    : (STEP_INDEX[key] ?? 0)
  if (index > STEP_INDEX.store && setupStatus === 'idle') return STEP_INDEX.store
  return index
}

const NO_PICKS = { companies: [], priceLists: [] }

// What still blocks Continue on a step, or '' when nothing does. An owner Frappe Cloud signed in
// without a password must set one here, or they cannot sign back in once this session ends.
export function missingField(stepKey, draft, { needsPassword = false, picks = NO_PICKS } = {}) {
  if (stepKey === 'you' && !draft.fullName.trim()) return 'fullName'
  if (stepKey === 'you' && needsPassword && !draft.password) return 'password'
  if (stepKey === 'store' && !draft.storeName.trim()) return 'storeName'
  if (stepKey === 'store' && !draft.storeCategory) return 'storeCategory'
  if (stepKey === 'store' && picks.companies.length && !draft.company) return 'company'
  if (stepKey === 'store' && picks.priceLists.length && !picks.priceLists.includes(draft.priceList)) return 'priceList'
  return ''
}

export function storePicks(existingStore, company) {
  if (!existingStore) return NO_PICKS
  const currency = existingStore.companies.find((row) => row.name === company)?.default_currency
  const priceLists = currency
    ? existingStore.price_lists.filter((row) => row.currency === currency).map((row) => row.name)
    : []
  return {
    companies: existingStore.company ? [] : existingStore.companies.map((row) => row.name),
    priceLists: priceLists.length > 1 ? priceLists : [],
  }
}

// The setup must have finished before the dashboard opens: every screen behind it reads the company.
export function canFinish(setupStatus) {
  return setupStatus === 'done'
}

// Mirrors frappe.utils.get_abbr with commera.onboarding's five-letter cap, which the server falls
// back to when the short code is left alone; the box only shows it as a placeholder. The server
// also numbers it past an abbreviation another company holds, which this cannot see.
export function abbreviate(name, maxLength = 5) {
  const words = String(name ?? '').trim().split(/\s+/).filter(Boolean)
  return words
    .map((word) => word[0])
    .join('')
    .slice(0, maxLength)
    .toUpperCase()
}

// Option lists arrive as plain strings; the pickers want label/value pairs.
export function toOptions(values) {
  return (values ?? []).map((value) => (typeof value === 'string' ? { label: value, value } : value))
}

// How long the setup poll waits before its next beat, or null once it should stop asking. The job
// usually takes about a minute, so two seconds keeps "Ready" prompt; past that the beat slows, and
// past ten minutes the tab stops polling a job that may have died with its worker.
export const SETUP_POLL = { fastMs: 2000, slowMs: 10000, slowAfterMs: 60000, stallAfterMs: 10 * 60000 }

export function setupPollDelay(elapsedMs) {
  if (elapsedMs > SETUP_POLL.stallAfterMs) return null
  return elapsedMs > SETUP_POLL.slowAfterMs ? SETUP_POLL.slowMs : SETUP_POLL.fastMs
}
