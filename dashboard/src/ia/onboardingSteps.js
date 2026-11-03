// The onboarding flow's shape, with no imports so tests/unit can load it under plain node.

// `focus` names the area of the store preview a step outlines; `optional` offers Skip.
export const STEPS = [
  { key: 'you', title: 'Welcome' },
  { key: 'store', title: 'Your store' },
  { key: 'brand', title: 'Your brand', focus: 'brand', optional: true },
  { key: 'theme', title: 'Pick a look', focus: 'theme' },
  { key: 'selling', title: 'Selling', focus: 'selling' },
  { key: 'products', title: 'Products', focus: 'products', optional: true },
  { key: 'done', title: '' },
]

export const STEP_INDEX = Object.fromEntries(STEPS.map((step, index) => [step.key, index]))

export function clampStep(index) {
  return Math.min(STEPS.length - 1, Math.max(0, Number.isInteger(index) ? index : 0))
}

// The step a reload resumes at. Every step after the store needs the store setup to have been
// started; a setup that never started (or a cache that forgot it) sends the owner back to start it.
export function resumeStep(savedIndex, setupStatus) {
  const index = clampStep(savedIndex)
  if (index > STEP_INDEX.store && setupStatus === 'idle') return STEP_INDEX.store
  return index
}

// What still blocks Continue on a step, or '' when nothing does. An owner Frappe Cloud signed in
// without a password must set one here, or they cannot sign back in once this session ends.
export function missingField(stepKey, draft, { needsPassword = false } = {}) {
  if (stepKey === 'you' && !draft.fullName.trim()) return 'fullName'
  if (stepKey === 'you' && needsPassword && !draft.password) return 'password'
  if (stepKey === 'store' && !draft.storeName.trim()) return 'storeName'
  if (stepKey === 'store' && !draft.storeCategory) return 'storeCategory'
  return ''
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

// Whole seconds since `since` (a Date.now() value), for the funnel's `duration_seconds`.
export function secondsSince(since, now = Date.now()) {
  return Math.max(0, Math.round((now - since) / 1000))
}
