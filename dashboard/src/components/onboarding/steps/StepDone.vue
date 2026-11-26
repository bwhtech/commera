<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { draft } from '../../../ia/onboarding'
import { SETUP_STAGES, STEP_INDEX, setupBuildLevel } from '../../../ia/onboardingSteps'
import { __ } from '../../../data/translation'
import { burstConfetti } from '../../../utils/confetti'
import { prefersReducedMotion } from '../../../utils/reveal'
import StoreCanvas from '../StoreCanvas.vue'

const props = defineProps({
  finishing: { type: Boolean, default: false },
  // The store setup's status: only `done` can finish, and a `failed` one is retried from the
  // alert above, so it must not read as a skeleton that will resolve on its own.
  setupStatus: { type: String, default: 'idle' },
  setupStage: { type: String, default: '' },
  look: { type: Object, required: true },
})
const emit = defineEmits(['finish', 'build'])

const CAPTIONS = [
  __('Laying the foundations…'),
  __('Hanging your sign…'),
  __('Chiselling the storefront…'),
  __('Polishing the shelves…'),
]
const FINAL_BUILD = SETUP_STAGES.length + 1
const LOCAL_BUILD = 2
const BUILD_DWELL_MS = 900
const WELCOME_DWELL_MS = 1800

const shownBuild = ref(0)
const isWelcome = ref(false)
const finishRequested = ref(false)
const confettiCanvas = ref(null)
let beatTimer = null
let lastBeatAt = Date.now()

const reachedBuild = computed(() => Math.max(LOCAL_BUILD, setupBuildLevel(props.setupStatus, props.setupStage)))
const isFailed = computed(() => props.setupStatus === 'failed')
const caption = computed(() => CAPTIONS[Math.min(shownBuild.value, CAPTIONS.length - 1)])
const storeName = computed(() => draft.storeName.trim())

function scheduleBeat(delay) {
  if (beatTimer) return
  beatTimer = setTimeout(beat, Math.max(0, delay - (Date.now() - lastBeatAt)))
}

function beat() {
  beatTimer = null
  if (isFailed.value) return
  lastBeatAt = Date.now()
  if (isWelcome.value) {
    finishRequested.value = true
    emit('finish')
    return
  }
  if (shownBuild.value === FINAL_BUILD) isWelcome.value = true
  else if (shownBuild.value < reachedBuild.value) shownBuild.value += 1
  else return
  scheduleBeat(isWelcome.value ? WELCOME_DWELL_MS : BUILD_DWELL_MS)
}

watch([reachedBuild, isFailed], () => scheduleBeat(BUILD_DWELL_MS), { immediate: true })
watch(shownBuild, (level) => emit('build', level), { immediate: true })
watch(
  confettiCanvas,
  (canvas) => {
    if (canvas && !prefersReducedMotion()) burstConfetti(canvas)
  },
  { flush: 'post' },
)
onBeforeUnmount(() => clearTimeout(beatTimer))
</script>

<template>
  <div class="space-y-6" :data-onboarding-build="isWelcome ? 'welcome' : shownBuild">
    <div
      class="h-72 overflow-hidden rounded-5 border border-outline-gray-2 lg:hidden"
      :data-theme="look.dark ? 'dark' : undefined"
    >
      <StoreCanvas :stage="STEP_INDEX.done" :look="look" :build="shownBuild" mobile />
    </div>

    <Transition
      mode="out-in"
      enter-active-class="transition-[opacity,transform] duration-300 ease-out-strong"
      enter-from-class="translate-y-1 opacity-0 motion-reduce:translate-y-0"
      leave-active-class="transition-opacity duration-150"
      leave-to-class="opacity-0"
    >
      <div v-if="isWelcome" key="welcome" class="relative">
        <div class="pointer-events-none absolute -inset-x-8 -top-40 h-80" aria-hidden="true">
          <canvas ref="confettiCanvas" class="size-full" />
        </div>
        <h1 class="relative text-3xl-semibold text-ink-gray-9">{{ __('Welcome to Commera') }}</h1>
        <p v-if="storeName" class="relative mt-2 text-p-base text-ink-gray-6">{{ storeName }}</p>
      </div>
      <p
        v-else
        :key="caption"
        class="text-3xl-semibold"
        :class="isFailed ? 'text-ink-red-6' : 'text-ink-gray-9'"
        aria-live="polite"
      >
        {{ caption }}
      </p>
    </Transition>

    <p v-if="isFailed" class="text-p-base text-ink-red-6">
      {{ __('Your store could not be set up. Retry it above, then come back here.') }}
    </p>
    <Button
      v-else-if="finishRequested && !finishing"
      variant="solid"
      size="md"
      class="w-full"
      :label="__('Go to Home')"
      @click="$emit('finish')"
    />
  </div>
</template>
