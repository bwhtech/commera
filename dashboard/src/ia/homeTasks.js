import { useStorage } from '@vueuse/core'

export const dismissedTasks = useStorage('commera:home-dismissed-tasks', [])

// Home clears this on mount; onboarding sets it again so its hand-off plays the entrance.
export const homeArrival = { playEntrance: true }

export function dismissTask(key) {
  if (!dismissedTasks.value.includes(key)) dismissedTasks.value = [...dismissedTasks.value, key]
}

export function restoreTasks() {
  dismissedTasks.value = []
}
