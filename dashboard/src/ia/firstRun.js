import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { stepsWithProgress } from '../data/firstRun'

const STORAGE_KEY = 'commera:welcome-seen'

export function hasSeenWelcome() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    // Private mode. Seen-by-default is the safe failure: replaying a full-screen
    // greeting on every load is worse than never showing it.
    return true
  }
}

export function markWelcomeSeen() {
  try {
    localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    /* private mode — the app still works, it just won't remember */
  }
}

export function forgetWelcomeSeen() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* private mode */
  }
}

const DISMISSED_KEY = 'commera:setup-dismissed'
const SKIPPED_KEY = 'commera:setup-skipped'

function readFlag(key) {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    // Private mode. Untouched is the safe failure: the panel can be closed again.
    return false
  }
}

function writeFlag(key, value) {
  try {
    if (value) localStorage.setItem(key, '1')
    else localStorage.removeItem(key)
  } catch {
    /* private mode */
  }
}

export const setupDismissed = ref(readFlag(DISMISSED_KEY))
export const setupSkipped = ref(readFlag(SKIPPED_KEY))

export function dismissSetup() {
  setupDismissed.value = true
  writeFlag(DISMISSED_KEY, true)
}

export function skipSetup() {
  setupSkipped.value = true
  writeFlag(SKIPPED_KEY, true)
}

export function reopenSetup() {
  setupDismissed.value = false
  writeFlag(DISMISSED_KEY, false)
}

// Banner and panel live in different trees, so the list they share is derived
// here rather than passed down.
export function useSetupSteps() {
  const route = useRoute()

  const doneCount = computed(() => {
    const done = Number(route.query.done)
    return Number.isInteger(done) ? done : null
  })

  const steps = computed(() => (doneCount.value === null ? [] : stepsWithProgress(doneCount.value)))
  const settingUp = computed(
    () => !setupSkipped.value && steps.value.length > 0 && steps.value.some((step) => !step.done),
  )

  return { steps, settingUp }
}
