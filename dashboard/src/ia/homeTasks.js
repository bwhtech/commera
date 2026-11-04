import { useStorage } from '@vueuse/core'

// Per browser, like the sidebar's collapsed state: a dismissed card is a preference, not store data.
export const dismissedTasks = useStorage('commera:home-dismissed-tasks', [])

// Home stages its entrance on a page load and on the hand-off from onboarding, which sets this
// again. Home consumes it on mount, so a visit from the sidebar opens at rest: it is opened many
// times a day.
export const homeArrival = { playEntrance: true }

export function dismissTask(key) {
  if (!dismissedTasks.value.includes(key)) dismissedTasks.value = [...dismissedTasks.value, key]
}

export function restoreTasks() {
  dismissedTasks.value = []
}
