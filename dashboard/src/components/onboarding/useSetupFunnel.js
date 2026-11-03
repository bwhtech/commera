import { onBeforeUnmount, onMounted, watch } from 'vue'
import { sendSetupEvent } from '../../data/setupFunnel'
import { STEPS, secondsSince } from '../../ia/onboardingSteps'

// The funnel as Frappe's wizard reports its own: started, each step completed or skipped with the
// time spent on it, going back, and leaving before the end. `currentStep` is a getter for the step
// on screen; `finishing()` marks the owner's own way out, so that leaving then is not abandoning.
export function useSetupFunnel(currentStep) {
  let shownAt = Date.now()
  let isFinishing = false

  watch(currentStep, () => (shownAt = Date.now()))

  const stepProperties = (key) => ({
    step: key,
    step_number: STEPS.findIndex((step) => step.key === key) + 1,
    total_steps: STEPS.length,
    duration_seconds: secondsSince(shownAt),
  })

  function onLeave() {
    if (isFinishing) return
    sendSetupEvent('left_setup', { step: currentStep(), duration_seconds: secondsSince(shownAt) }, { keepalive: true })
  }
  onMounted(() => window.addEventListener('pagehide', onLeave))
  onBeforeUnmount(() => window.removeEventListener('pagehide', onLeave))

  return {
    started: ({ resumed }) => {
      shownAt = Date.now()
      sendSetupEvent('started_setup', { step: currentStep(), resumed, total_steps: STEPS.length })
    },
    settled: (key, action) =>
      sendSetupEvent(action === 'skip' ? 'skipped_setup_step' : 'completed_setup_step', stepProperties(key)),
    wentBack: (fromKey, toKey) => sendSetupEvent('went_back_in_setup', { from_step: fromKey, to_step: toKey }),
    finishing: () => (isFinishing = true),
    finishFailed: () => (isFinishing = false),
  }
}
