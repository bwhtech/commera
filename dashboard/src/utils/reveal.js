import { onMounted, ref } from 'vue'

// Ease-out-expo: fast out of the gate, long settle.
export const REVEAL_EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'

export function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

// Starting settled is what honours reduced motion: a transition fires only on a
// change of state, so an element mounted in its final state never animates.
export function useReveal(delay = 60) {
  const shown = ref(prefersReducedMotion())
  onMounted(() => {
    if (shown.value) return
    setTimeout(() => (shown.value = true), delay)
  })
  return shown
}
