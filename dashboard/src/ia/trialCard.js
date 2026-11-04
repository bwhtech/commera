import { computed } from 'vue'
import { useStorage } from '@vueuse/core'
import { trialNotice } from '../data/cloudBilling'

const DISMISS_MS = 24 * 60 * 60 * 1000

const dismissedAt = useStorage('commera:trial-card-dismissed-at', 0)

// An ended trial ignores the dismissal: its notice is not dismissible.
export const isTrialCardShown = computed(
  () => Boolean(trialNotice.value) && !(trialNotice.value.dismissible && Date.now() - dismissedAt.value < DISMISS_MS),
)

export function dismissTrialCard() {
  dismissedAt.value = Date.now()
}
