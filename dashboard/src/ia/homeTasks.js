import { useStorage } from '@vueuse/core'

export const dismissedTasks = useStorage('commera:home-dismissed-tasks', [])

// Home clears this on mount. `load` plays the short entrance; onboarding's hand-off sets `onboarding`.
export const homeArrival = { entrance: 'load' }

export function dismissTask(key) {
  if (!dismissedTasks.value.includes(key)) dismissedTasks.value = [...dismissedTasks.value, key]
}

export function restoreTasks() {
  dismissedTasks.value = []
}
