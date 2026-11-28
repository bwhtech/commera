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

// The step a reload resumes at. A setup that never started starts over at the welcome step: the
// saved step outlives a site whose database was reset, and would skip the name.
export function resumeStep(saved, setupStatus) {
  if (setupStatus === 'idle') return STEP_INDEX.you
  const key = /^\d+$/.test(String(saved ?? '')) ? LEGACY_STEP_KEYS[Number(saved)] : saved
  if (RETIRED_STEP_KEYS.includes(key)) return STEP_INDEX[setupStatus === 'done' ? 'done' : 'store']
  return STEP_INDEX[key] ?? 0
}

const NO_PICKS = { companies: [], priceLists: [] }

// What still blocks Continue on a step, or '' when nothing does. An owner Frappe Cloud signed in
// without a password must set one here, or they cannot sign back in once this session ends.
export function missingField(stepKey, draft, { needsPassword = false, picks = NO_PICKS } = {}) {
  if (stepKey === 'you' && !draft.fullName.trim()) return 'fullName'
  if (stepKey === 'you' && needsPassword && !draft.password) return 'password'
  if (stepKey === 'store' && !draft.storeName.trim()) return 'storeName'
  if (stepKey === 'store' && !draft.existingStore && !draft.country) return 'country'
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

export const SETUP_STAGES = ['company', 'storefront', 'payments']

export const FINAL_BUILD = SETUP_STAGES.length + 1

export function setupBuildLevel(setupStatus, stage) {
  if (setupStatus === 'done') return FINAL_BUILD
  return SETUP_STAGES.indexOf(stage) + 1
}

// How long the store preview holds its current piece, or null to wait for the setup. The setup wizard
// clears the cache that carries the stage, so the stages reach the poll together with `done`: the
// preview paces itself up to the piece before the products rather than sit on one for the whole wait.
export const BUILD_DWELL = { reachedMs: 900, pacedMs: 3000, welcomeMs: 1800 }

export function buildDwell(shownBuild, reachedBuild, isWelcome) {
  if (isWelcome) return BUILD_DWELL.welcomeMs
  if (shownBuild < reachedBuild || shownBuild === FINAL_BUILD) return BUILD_DWELL.reachedMs
  if (shownBuild < FINAL_BUILD - 1) return BUILD_DWELL.pacedMs
  return null
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
