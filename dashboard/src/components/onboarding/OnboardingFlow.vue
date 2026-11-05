<script setup>
/**
 * First-run onboarding, covering the whole app until it is finished: one step at a time on the
 * right, the store building itself on the left. App.vue renders this instead of the shell.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Button, Spinner } from 'frappe-ui'
import { bootValue } from '../../data/boot'
import {
  completeOnboarding,
  loadOnboarding,
  loadStoreProducts,
  onboarding,
  onboardingLoadError,
  saveBrand,
  saveProfile,
  saveSelling,
  startStoreSetup,
  storeSetup,
} from '../../data/onboarding'
import { useTheme } from '../../data/theme'
import { addProduct } from '../../data/addProduct'
import { imp as productImport } from '../../data/importFlow'
import { homeArrival } from '../../ia/homeTasks'
import {
  adoptRecord,
  closeOnboarding,
  currentStep,
  draft,
  flow,
  forgetOnboardingStep,
  goToStep,
  lookFor,
  readSavedStep,
} from '../../ia/onboarding'
import { canFinish, missingField, resumeStep } from '../../ia/onboardingSteps'
import { useEntrance } from '../../utils/reveal'
import OnboardingPreview from './OnboardingPreview.vue'
import StepYou from './steps/StepYou.vue'
import StepStore from './steps/StepStore.vue'
import StepBrand from './steps/StepBrand.vue'
import StepTheme from './steps/StepTheme.vue'
import StepSelling from './steps/StepSelling.vue'
import StepProducts from './steps/StepProducts.vue'
import StepDone from './steps/StepDone.vue'

const STEP_COMPONENTS = {
  you: StepYou,
  store: StepStore,
  brand: StepBrand,
  theme: StepTheme,
  selling: StepSelling,
  products: StepProducts,
  done: StepDone,
}

// One class per step, listed so Tailwind can see them. A transform, not a width, so the fill
// never touches layout; the first step shows a sliver rather than an empty track.
const PROGRESS = ['scale-x-[0.04]', 'scale-x-[0.17]', 'scale-x-[0.33]', 'scale-x-50', 'scale-x-[0.67]', 'scale-x-[0.83]', 'scale-x-100']

// Forward enters from the right and leaves to the left; Back plays the same path in reverse.
const SLIDES = {
  forward: { enter: 'translate-x-4 opacity-0 motion-reduce:translate-x-0', leave: '-translate-x-4 opacity-0 motion-reduce:translate-x-0' },
  back: { enter: '-translate-x-4 opacity-0 motion-reduce:translate-x-0', leave: 'translate-x-4 opacity-0 motion-reduce:translate-x-0' },
}

const router = useRouter()
const { themes, load: loadThemes, activate: activateTheme } = useTheme()
const activeTheme = computed(() => themes.value.find((theme) => theme.live)?.name ?? '')

const saving = ref(false)
const finishing = ref(false)
const retrying = ref(false)

const record = computed(() => onboarding.value)
// The column mounts empty while the record loads, so its entrance waits for the record.
const entered = useEntrance(() => Boolean(record.value))
const step = computed(() => currentStep.value)
const slide = computed(() => (flow.direction > 0 ? SLIDES.forward : SLIDES.back))
const needsPassword = computed(() => Boolean(record.value?.needs_password))
const look = computed(() => lookFor(draft.theme, themes.value.map((theme) => theme.name)))
const isReady = computed(() => canFinish(storeSetup.status))

const stepProps = computed(() => {
  if (step.value.key === 'you') return { needsPassword: needsPassword.value }
  if (step.value.key === 'store') return { record: record.value }
  if (step.value.key === 'done') return { finishing: finishing.value, isReady: isReady.value }
  return {}
})

const title = computed(() => {
  if (step.value.key === 'you') return draft.fullName ? `Welcome, ${draft.fullName.trim().split(' ')[0]}` : step.value.title
  if (step.value.key === 'done') return `${draft.storeName.trim() || 'Your store'} is ready`
  return step.value.title
})

async function load() {
  const data = await loadOnboarding()
  if (!data) return
  adoptRecord(data)
  goToStep(resumeStep(readSavedStep(), storeSetup.status))
}

onMounted(async () => {
  await Promise.all([load(), loadThemes()])
  draft.theme = draft.theme || activeTheme.value || ''
})

function storeSetupValues() {
  return {
    store_name: draft.storeName.trim(),
    store_category: draft.storeCategory,
    country: draft.country,
    currency: draft.currency,
    time_zone: draft.timeZone,
    chart_of_accounts: draft.chartOfAccounts,
    fiscal_year_start_month: draft.fiscalYearStartMonth || undefined,
    company_abbr: draft.companyAbbr.trim() || undefined,
  }
}

async function activatePickedTheme() {
  if (!draft.theme || draft.theme === activeTheme.value) return true
  return activateTheme(draft.theme)
}

// What Continue writes before moving on. A step missing here has nothing of its own to save.
const SAVES = {
  you: () => saveProfile(draft),
  store: () => startStoreSetup(storeSetupValues()),
  brand: () => saveBrand(draft),
  theme: activatePickedTheme,
  selling: () => saveSelling(draft),
}

async function next() {
  if (missingField(step.value.key, draft, { needsPassword: needsPassword.value })) {
    flow.showErrors = true
    return
  }
  saving.value = true
  const saved = await (SAVES[step.value.key]?.() ?? true)
  saving.value = false
  if (saved) goToStep(flow.index + 1)
}

async function retrySetup() {
  retrying.value = true
  await startStoreSetup(storeSetupValues())
  retrying.value = false
}

async function finish() {
  if (!isReady.value) return
  finishing.value = true
  const completed = await completeOnboarding()
  if (!completed) {
    finishing.value = false
    return
  }
  homeArrival.playEntrance = true
  // format.js reads the boot's currency once at load. Setup may have changed it, and then every
  // money figure would wear the old symbol until a reload.
  if (bootValue('currency', '') !== draft.currency) {
    // Not closeOnboarding(): the shell would flash in with the stale boot before the reload lands.
    forgetOnboardingStep()
    window.location.assign('/commera/')
    return
  }
  // An add-product dialog closed during onboarding left the URL on that product.
  await router.replace('/')
  closeOnboarding()
}

// Products made from the onboarding's dialogs appear in the preview once each dialog closes.
watch(
  () => [addProduct.open, productImport.open, storeSetup.status, step.value.key],
  ([addOpen, importOpen, status, key]) => {
    if (!addOpen && !importOpen && status === 'done' && key === 'products') loadStoreProducts()
  },
)
</script>

<template>
  <div class="fixed inset-0 z-10 flex bg-surface-base" data-onboarding>
    <aside class="hidden min-w-0 flex-1 items-center justify-center bg-surface-gray-2 p-10 lg:flex">
      <OnboardingPreview :focus="step.focus" :stage="flow.index" :look="look" />
    </aside>

    <main class="flex h-full w-full flex-col lg:w-[480px] lg:shrink-0 xl:w-[520px]">
      <!-- Back sits alone in the corner, as in Raven's setup; the badge only ever shares the row. -->
      <header class="flex h-14 shrink-0 items-center px-4">
        <Button
          v-if="flow.index > 0 && step.key !== 'done'"
          variant="ghost"
          size="md"
          icon-left="lucide-arrow-left"
          label="Back"
          :disabled="saving"
          @click="goToStep(flow.index - 1)"
        />
        <div class="ml-auto" aria-live="polite">
          <Transition
            mode="out-in"
            enter-active-class="transition-[opacity,transform] duration-300 ease-out-strong"
            enter-from-class="scale-95 opacity-0 motion-reduce:scale-100"
            leave-active-class="transition-opacity duration-150"
            leave-to-class="opacity-0"
          >
            <span
              v-if="storeSetup.status === 'running'"
              key="running"
              class="flex items-center gap-1.5 text-sm text-ink-gray-5"
              data-onboarding-setup="running"
              title="Creating your company, books and warehouse"
            >
              <Spinner class="size-3.5" /> Setting up
            </span>
            <span
              v-else-if="storeSetup.status === 'done'"
              key="done"
              class="flex items-center gap-1.5 text-sm text-ink-green-6"
              data-onboarding-setup="done"
            >
              <span class="lucide-circle-check size-3.5" aria-hidden="true" /> Ready
            </span>
            <span
              v-else-if="storeSetup.status === 'failed'"
              key="failed"
              class="flex items-center gap-1.5 text-sm text-ink-red-6"
              data-onboarding-setup="failed"
            >
              <span class="lucide-circle-alert size-3.5" aria-hidden="true" /> Setup failed
            </span>
          </Transition>
        </div>
      </header>

      <div v-if="!record" class="flex flex-1 items-center justify-center">
        <div v-if="onboardingLoadError" class="space-y-3 text-center">
          <p class="text-base text-ink-gray-6">Could not load your setup</p>
          <Button label="Try again" @click="load" />
        </div>
        <Spinner v-else class="size-5 text-ink-gray-5" />
      </div>

      <div v-else class="mx-auto flex min-h-0 w-full max-w-sm flex-1 flex-col overflow-y-auto px-4 pb-10 pt-[10vh] sm:px-1">
        <div
          class="mb-8 h-[3px] shrink-0 overflow-hidden rounded-full bg-surface-gray-2 transition-[opacity,transform] delay-200 duration-500 ease-out-strong"
          :class="entered && step.key !== 'done' ? 'translate-y-0 opacity-100' : 'translate-y-2.5 opacity-0 motion-reduce:translate-y-0'"
        >
          <div
            class="h-full origin-left rounded-full bg-surface-gray-10 transition-transform duration-500 ease-in-out-strong"
            :class="PROGRESS[flow.index]"
          />
        </div>

        <Alert
          v-if="storeSetup.status === 'failed'"
          class="mb-6"
          theme="red"
          :title="storeSetup.error || 'Store setup failed'"
          :primary-action="{ label: 'Retry', loading: retrying, onClick: retrySetup }"
        />

        <div
          class="flex flex-1 flex-col transition-[opacity,transform] delay-300 duration-500 ease-out-strong"
          :class="entered ? 'translate-y-0 opacity-100' : 'translate-y-2.5 opacity-0 motion-reduce:translate-y-0'"
        >
          <Transition
            mode="out-in"
            enter-active-class="transition-[opacity,transform] duration-300 ease-out-strong"
            :enter-from-class="slide.enter"
            leave-active-class="transition-[opacity,transform] duration-150 ease-out-strong"
            :leave-to-class="slide.leave"
          >
            <form :key="step.key" class="flex flex-1 flex-col" :data-onboarding-step="step.key" @submit.prevent="next">
              <div
                v-if="step.key === 'done'"
                class="mb-4 flex size-10 items-center justify-center rounded-full bg-surface-green-2 text-ink-green-6"
              >
                <span class="lucide-party-popper size-5" aria-hidden="true" />
              </div>
              <h1 class="mb-7 text-3xl-semibold text-ink-gray-9">{{ title }}</h1>

              <component :is="STEP_COMPONENTS[step.key]" v-bind="stepProps" @finish="finish" />

              <div v-if="step.key !== 'done'" class="mt-auto space-y-1 pt-8">
                <Button type="submit" variant="solid" size="md" label="Continue" class="w-full" :loading="saving" />
                <Button v-if="step.optional" variant="ghost" size="md" label="Skip" class="w-full" :disabled="saving" @click="goToStep(flow.index + 1)" />
              </div>
            </form>
          </Transition>
        </div>
      </div>
    </main>
  </div>
</template>
