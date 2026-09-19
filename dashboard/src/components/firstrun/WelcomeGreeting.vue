<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { prefersReducedMotion, REVEAL_EASE } from '../../utils/reveal'

const emit = defineEmits(['exiting', 'dismiss'])

defineOptions({ inheritAttrs: false })

// The path is authored in writing order, so walking stroke-dashoffset to zero
// writes the word left to right. Re-authoring it out of order breaks that.
const DRAW_MS = 1400
const HOLD_MS = 260
const EXIT_MS = 560

// Shorter than the exit on purpose: the panel moves while the greeting clears,
// because sequencing the two leaves a dead gap.
const HANDOVER_MS = 220

const stage = ref(null)
const overlay = ref(null)
const wordmark = ref(null)
const timers = []
let leaving = false

// Clearing the transform is what stops #app being a containing block for
// everything fixed inside it. Also runs on unmount, since the timer is cancelled.
function resetPage() {
  const root = document.getElementById('app')
  if (!root) return
  root.style.transition = ''
  root.style.transform = ''
  root.style.transformOrigin = ''
  root.style.opacity = ''
}

// #app is the target rather than a wrapper: greeting and panel are teleported to
// body, and a transformed ancestor would capture their fixed positioning.
function arrivePage(duration) {
  const root = document.getElementById('app')
  if (!root) return

  root.style.transition = 'none'
  root.style.transformOrigin = 'center'
  root.style.transform = 'scale(0.985)'
  root.style.opacity = '0.7'
  void root.getBoundingClientRect()

  root.style.transition = `transform ${duration}ms ${REVEAL_EASE}, opacity ${duration}ms ${REVEAL_EASE}`
  root.style.transform = 'scale(1)'
  root.style.opacity = '1'

  timers.push(setTimeout(resetPage, duration + 40))
}

function finish() {
  if (leaving) return
  leaving = true

  stage.value.style.transition = `transform ${EXIT_MS}ms ${REVEAL_EASE}, opacity ${EXIT_MS}ms ${REVEAL_EASE}`
  stage.value.style.transform = 'translateY(-16px)'
  stage.value.style.opacity = '0'

  overlay.value.style.transition = `opacity ${EXIT_MS}ms ${REVEAL_EASE}`
  overlay.value.style.opacity = '0'
  overlay.value.style.pointerEvents = 'none'

  arrivePage(EXIT_MS)

  timers.push(setTimeout(() => emit('exiting'), HANDOVER_MS))
  timers.push(setTimeout(() => emit('dismiss'), EXIT_MS + 60))
}

onMounted(() => {
  if (prefersReducedMotion()) {
    emit('exiting')
    emit('dismiss')
    return
  }

  const path = wordmark.value
  const length = path.getTotalLength()
  path.style.strokeDasharray = `${length}`
  path.style.strokeDashoffset = `${length}`

  // Read back before changing it, or the browser coalesces both writes into one
  // paint and the stroke simply appears finished.
  void path.getBoundingClientRect()

  path.style.transition = `stroke-dashoffset ${DRAW_MS}ms cubic-bezier(0.4, 0, 0.2, 1)`
  path.style.strokeDashoffset = '0'

  timers.push(setTimeout(finish, DRAW_MS + HOLD_MS))
  window.addEventListener('keydown', finish)
})

onBeforeUnmount(() => {
  timers.forEach(clearTimeout)
  window.removeEventListener('keydown', finish)
  resetPage()
})
</script>

<template>
  <Teleport to="body">
    <div
      ref="overlay"
      class="fixed inset-0 z-50 grid cursor-pointer place-items-center overflow-hidden bg-surface-base"
      role="presentation"
      @click="finish"
    >
      <div ref="stage">
        <svg
          class="w-[min(34rem,78vw)] text-ink-gray-9"
          viewBox="55 28 545 135"
          fill="none"
          aria-label="Welcome to Commera"
        >
          <path
            ref="wordmark"
            d="M 172 66 C 156 46 116 40 96 60 C 72 82 74 118 100 134 C 120 145 152 140 168 128 C 180 118 190 94 204 90 C 218 87 230 100 228 116 C 226 132 210 142 197 136 C 186 131 184 116 194 106 C 206 96 222 92 238 98 C 240 114 240 128 240 140 C 243 108 254 92 267 94 C 279 97 281 119 281 140 C 284 109 295 92 308 94 C 320 97 322 119 322 140 C 325 130 330 122 337 98 C 339 114 339 128 339 140 C 342 108 353 92 366 94 C 378 97 380 119 380 140 C 383 109 394 92 407 94 C 419 97 421 119 421 140 C 422 130 426 124 432 119 C 440 110 452 104 462 108 C 470 111 470 121 460 123 C 448 125 436 122 432 118 C 438 136 456 144 472 137 C 478 134 482 130 486 126 C 490 116 493 102 495 92 C 500 104 509 110 519 106 C 526 103 530 100 534 97 C 542 90 553 96 553 112 C 553 128 543 138 532 134 C 522 130 521 114 530 106 C 539 98 551 100 554 114 C 556 126 557 134 558 140 C 564 136 572 130 582 123"
            stroke="currentColor"
            stroke-width="6.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </div>
    </div>
  </Teleport>
</template>
