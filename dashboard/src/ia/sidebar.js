import { computed, ref } from 'vue'
import { ia } from './store'

const holds = ref(0)
const expandedWhileHeld = ref(false)

export const sidebarCollapsed = computed(() => (holds.value > 0 ? !expandedWhileHeld.value : ia.sidebarCollapsed))

export function toggleSidebar() {
  if (holds.value > 0) expandedWhileHeld.value = !expandedWhileHeld.value
  else ia.sidebarCollapsed = !ia.sidebarCollapsed
}

export function holdSidebarCollapsed() {
  holds.value += 1
  let released = false
  return function release() {
    if (released) return
    released = true
    holds.value -= 1
    if (holds.value === 0) expandedWhileHeld.value = false
  }
}
