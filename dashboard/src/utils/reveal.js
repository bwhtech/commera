import { onMounted, ref, watch } from 'vue'

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

// Unlike useReveal, this starts hidden under reduced motion too: the entrance still fades there,
// and the `motion-reduce:` classes on the element drop only the movement. `isReady` holds the
// entrance back for content that mounts before its data. Two frames, because a flag flipped in the
// mounting frame lands in the same style pass and nothing transitions.
export function useEntrance(isReady = () => true) {
  const entered = ref(false)
  const enter = () => requestAnimationFrame(() => requestAnimationFrame(() => (entered.value = true)))
  onMounted(() => {
    if (isReady()) return enter()
    const stop = watch(isReady, (ready) => {
      if (!ready) return
      stop()
      enter()
    })
  })
  return entered
}
