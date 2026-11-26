<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button, Progress, Spinner } from 'frappe-ui'
import { draft } from '../../../ia/onboarding'
import { SETUP_STAGES, completedSetupStages } from '../../../ia/onboardingSteps'
import { __ } from '../../../data/translation'

const props = defineProps({
  finishing: { type: Boolean, default: false },
  // The store setup's status: only `done` can finish, and a `failed` one is retried from the
  // alert above, so it must not read as a skeleton that will resolve on its own.
  setupStatus: { type: String, default: 'idle' },
  setupStage: { type: String, default: '' },
})
const emit = defineEmits(['finish'])

const STAGE_LABELS = {
  company: __('Creating your store'),
  storefront: __('Chiselling the storefront'),
  payments: __('Getting everything ready'),
}
const STAGE_DWELL_MS = 900
const WELCOME_DWELL_MS = 1400

const shownStages = ref(0)
const phase = ref('stages')
const finishRequested = ref(false)
let beatTimer = null
let lastBeatAt = Date.now()

const reachedStages = computed(() => completedSetupStages(props.setupStatus, props.setupStage))
const isFailed = computed(() => props.setupStatus === 'failed')
const storeName = computed(() => draft.storeName.trim())
const heading = computed(() => {
  if (isFailed.value) return __('Almost there')
  if (phase.value === 'welcome') return __('Welcome to {0}', [storeName.value])
  if (phase.value === 'ready') return __('Are you ready?')
  return STAGE_LABELS[SETUP_STAGES[shownStages.value]]
})

function scheduleBeat(delay) {
  if (beatTimer) return
  beatTimer = setTimeout(beat, Math.max(0, delay - (Date.now() - lastBeatAt)))
}

function beat() {
  beatTimer = null
  if (isFailed.value) return
  lastBeatAt = Date.now()
  if (phase.value === 'welcome') {
    finishRequested.value = true
    emit('finish')
    return
  }
  if (phase.value === 'ready') phase.value = 'welcome'
  else if (shownStages.value < reachedStages.value) shownStages.value += 1
  else return
  if (shownStages.value === SETUP_STAGES.length && phase.value === 'stages') phase.value = 'ready'
  scheduleBeat(phase.value === 'welcome' ? WELCOME_DWELL_MS : STAGE_DWELL_MS)
}

watch([reachedStages, isFailed], () => scheduleBeat(STAGE_DWELL_MS), { immediate: true })
onBeforeUnmount(() => clearTimeout(beatTimer))

function stageState(index) {
  if (index < shownStages.value) return 'done'
  if (index > shownStages.value) return 'pending'
  return isFailed.value ? 'failed' : 'active'
}
</script>

<template>
  <div class="space-y-6" :data-onboarding-progress="phase">
    <Transition
      mode="out-in"
      enter-active-class="transition-[opacity,transform] duration-300 ease-out-strong"
      enter-from-class="translate-y-1 opacity-0 motion-reduce:translate-y-0"
      leave-active-class="transition-opacity duration-150"
      leave-to-class="opacity-0"
    >
      <h1 :key="heading" class="text-3xl-semibold text-ink-gray-9" aria-live="polite">{{ heading }}</h1>
    </Transition>

    <Progress :value="Math.round((shownStages / SETUP_STAGES.length) * 100)" size="md" />

    <ul class="space-y-3">
      <li
        v-for="(stage, index) in SETUP_STAGES"
        :key="stage"
        class="flex items-center gap-2.5 text-base transition-colors duration-300"
        :class="stageState(index) === 'pending' ? 'text-ink-gray-4' : 'text-ink-gray-8'"
        :data-onboarding-stage="stageState(index)"
      >
        <span v-if="stageState(index) === 'done'" class="lucide-circle-check size-4 shrink-0 text-ink-green-6" aria-hidden="true" />
        <span v-else-if="stageState(index) === 'failed'" class="lucide-circle-alert size-4 shrink-0 text-ink-red-6" aria-hidden="true" />
        <Spinner v-else-if="stageState(index) === 'active'" class="size-4 shrink-0" />
        <span v-else class="lucide-circle size-4 shrink-0" aria-hidden="true" />
        {{ STAGE_LABELS[stage] }}
      </li>
    </ul>

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
    <p v-else class="flex items-start gap-2 text-p-base text-ink-gray-6">
      <span class="lucide-lock mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {{ __('Only you can see it for now. Publish it from Home when you are ready.') }}
    </p>
  </div>
</template>
