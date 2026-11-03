import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { setupSteps, setupStepsDone } from '../data/setupState'
import { useTelemetry } from '../telemetry'

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

const telemetry = useTelemetry()

export function dismissSetup() {
  setupDismissed.value = true
  writeFlag(DISMISSED_KEY, true)
  telemetry.capture('setup_dismissed', { steps_done: setupStepsDone.value })
}

export function skipSetup() {
  setupSkipped.value = true
  writeFlag(SKIPPED_KEY, true)
  telemetry.capture('setup_skipped', { steps_done: setupStepsDone.value })
}

// `surface` is `panel` or `banner`, docs/telemetry.md's `setup_step_opened.surface`.
export function captureSetupStepOpened(step, surface) {
  telemetry.capture('setup_step_opened', { step: step.key, surface, steps_done: setupStepsDone.value })
}

export function reopenSetup() {
  setupDismissed.value = false
  writeFlag(DISMISSED_KEY, false)
}

// Banner and panel live in different trees, so the list they share is derived
// here rather than passed down. The screen that shows them calls loadSetupState().
// The checklist is still a preview: it shows only with `?setup` (or `?replay`) until it is turned
// on for every store, so stores set up before onboarding existed do not get it unasked.
export function useSetupSteps() {
  const route = useRoute()
  const isPreview = computed(() => 'setup' in route.query || 'replay' in route.query)
  const settingUp = computed(
    () => isPreview.value && !setupSkipped.value && setupSteps.value.some((step) => !step.done),
  )
  return { steps: setupSteps, settingUp }
}
