// Which setup steps a store has done, from the server. The sidebar banner and the dashboard's panel
// live in different trees and read this one answer, so their ticks never disagree.
import { computed } from 'vue'
import { useAdminRead } from './api'
import { isAdmin } from './boot'
import { countStepsDone, stepsFromState } from './firstRun'

// Quiet: the checklist is a hint beside the work, and a failed read leaves it hidden rather than
// toasting over every page.
const setupStateRequest = useAdminRead('onboarding.get_setup_state', { immediate: false, quiet: true })

// Empty until the server answers: an unread state would show every step as not done.
export const setupSteps = computed(() => (setupStateRequest.data ? stepsFromState(setupStateRequest.data) : []))
export const setupStepsDone = computed(() => countStepsDone(setupStateRequest.data))

// Re-read on every visit to a screen that shows it: a step is done somewhere else in the app. The
// banner and the panel mount together on the dashboard, and a second fetch would abort the first.
export function loadSetupState() {
  if (isAdmin && !setupStateRequest.loading) setupStateRequest.fetch()
}
