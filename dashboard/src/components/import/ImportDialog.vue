<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog, Spinner, toast } from 'frappe-ui'
import { DialogDescription, DialogTitle } from 'reka-ui'
import { canChangeStep, closeImport, imp, isMappingChecked, steps } from '../../data/importFlow'
import { loadErpnextPreview } from '../../data/erpnextImport'
import { importLabel } from '../../data/importCounts'
import { fieldLabel, stillNeeded } from '../../data/importMapping'
import ImportStepNav from './ImportStepNav.vue'
import SourceStep from './steps/SourceStep.vue'
import UploadStep from './steps/UploadStep.vue'
import MapStep from './steps/MapStep.vue'
import ImagesStep from './steps/ImagesStep.vue'
import ReviewStep from './steps/ReviewStep.vue'
import RunStep from './steps/RunStep.vue'
import ErpnextPickStep from './steps/ErpnextPickStep.vue'
import ErpnextRunStep from './steps/ErpnextRunStep.vue'
import { __ } from '../../data/translation'

const stepComponents = {
  csv: { source: SourceStep, upload: UploadStep, map: MapStep, images: ImagesStep, review: ReviewStep, run: RunStep },
  erpnext: { source: SourceStep, pick: ErpnextPickStep, run: ErpnextRunStep },
}

// The step list depends on whether ERPNext has items to offer, so the flow waits for that answer
// before showing a step: deciding later would shift every step index under the merchant.
watch(
  () => imp.open && imp.hasSourceChoice === null,
  async (isWaiting) => {
    if (!isWaiting) return
    await loadErpnextPreview()
    if (imp.hasSourceChoice === null) imp.hasSourceChoice = imp.erpnext.importableCount > 0
  },
  { immediate: true },
)

const isReady = computed(() => imp.hasSourceChoice !== null)

// One scroll box serves every step, so a new step would otherwise open where the last one was left.
const body = ref(null)
watch(
  () => imp.step,
  () => body.value?.scrollTo({ top: 0 }),
)
const stepKey = computed(() => steps.value[imp.step]?.key)
const current = computed(() => stepComponents[imp.source][stepKey.value])

const erpnextSelected = computed(() => imp.erpnext.selected.length)

const assignedPhotos = computed(() =>
  Object.values(imp.imageAssignments).reduce((total, fileUrls) => total + fileUrls.length, 0),
)

function mapStepBlocker() {
  if (imp.phase === 'checking') return __('Checking your columns…')
  if (imp.checkError) return __('Your columns could not be checked. Try again.')
  const missing = stillNeeded(imp.mapping, imp.defaultCollection, isMappingChecked.value ? imp.missing : [])
  if (missing.includes('collection') && missing.length === 1) return __('Pick a collection for your products.')
  if (missing.length) return __('Match a column to {0} to continue.', [missing.map(fieldLabel).join(', ')])
  if (!isMappingChecked.value) return __('Checking your columns…')
  if (!imp.counts.total) return __('Your file has no product rows. Add some and upload it again.')
  return ''
}

// Why Continue is off, in one line, or '' when it is on.
const blockedReason = computed(() => {
  if (imp.phase === 'parsing') return __('Reading your file…')
  if (imp.phase === 'matching' || imp.phase === 'uploading') return __('Adding your photos…')
  if (stepKey.value === 'upload' && !imp.parsed) return __('Upload a file to continue.')
  if (stepKey.value === 'map') return mapStepBlocker()
  // run_import with nothing ready writes nothing.
  if (stepKey.value === 'review' && !imp.counts.ready) return __('No rows are ready. Fix your file and upload it again.')
  if (stepKey.value === 'pick' && !imp.erpnext.selectionReady) return __('Loading your items…')
  if (stepKey.value === 'pick' && !erpnextSelected.value) return __('Pick at least one item.')
  return ''
})

const canContinue = computed(() => canChangeStep.value && !blockedReason.value)

const nextLabel = computed(() => {
  if (stepKey.value === 'images') return assignedPhotos.value ? __('Continue') : __('Skip photos')
  if (stepKey.value === 'review') return importLabel(imp.counts)
  if (stepKey.value === 'pick') return erpnextSelected.value === 1 ? __('Import 1 item') : __('Import {0} items', [erpnextSelected.value])
  return __('Continue')
})

const startsImport = computed(() => stepKey.value === 'review' || stepKey.value === 'pick')

const onLastStep = computed(() => imp.step === steps.value.length - 1)

function next() {
  if (canContinue.value && imp.step < steps.value.length - 1) imp.step += 1
}

function back() {
  if (canChangeStep.value && imp.step > 0) imp.step -= 1
}

// Closing never cancels a request: a run keeps writing, and reopening shows how it ended.
function close() {
  if (imp.phase === 'running') toast.info(__('The import keeps running. Reopen Import to see how it went.'))
  closeImport()
}
</script>

<template>
  <Dialog
    v-model:open="imp.open"
    size="5xl"
    position="top"
    padding-top="2rem"
    bare
    :dismissible="false"
    @update:open="(v) => (v ? null : close())"
  >
    <!-- The panel has to fit the window with its own footer visible: the
         dialog's own margins take 8rem, everything else is the body's scroll. dvh, not vh: on a
         phone vh is the height with the address bar hidden, which would push the footer off. -->
    <div class="flex max-h-[calc(100dvh-8rem)] flex-col">
      <div class="space-y-3 border-b border-outline-gray-1 px-6 pb-4 pt-3">
        <div class="flex items-center gap-3">
          <!-- bare drops frappe-ui's own header, so the title and description are wired to the
               dialog through the same reka primitives it would have used. -->
          <DialogTitle as="h2" class="text-base-semibold text-ink-gray-8">{{ __('Import products') }}</DialogTitle>
          <span v-if="imp.phase === 'running'" class="text-sm text-ink-gray-5">{{ __('Import running…') }}</span>
          <Button class="ms-auto" variant="ghost" icon="lucide-x" :label="__('Close')" @click="close" />
        </div>
        <ImportStepNav v-if="isReady" />
        <DialogDescription class="sr-only">
          {{ isReady ? __('Step {0} of {1}: {2}', [imp.step + 1, steps.length, steps[imp.step]?.label]) : __('Loading…') }}
        </DialogDescription>
      </div>

      <div ref="body" v-scroll-fade class="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <component :is="current" v-if="isReady" @next="next" />
        <div v-else class="flex justify-center py-14"><Spinner class="size-5" /></div>
      </div>

      <div
        v-if="isReady && !onLastStep"
        class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-outline-gray-1 bg-surface-gray-1 px-6 py-4"
      >
        <Button
          v-if="imp.step > 0"
          icon-left="lucide-arrow-left rtl:-scale-x-100"
          :label="__('Back')"
          :disabled="!canChangeStep"
          @click="back"
        />
        <Button
          class="order-2 ms-auto sm:order-3"
          variant="solid"
          theme="gray"
          :disabled="!canContinue"
          :label="nextLabel"
          :icon-right="startsImport ? undefined : 'lucide-arrow-right rtl:-scale-x-100'"
          @click="next"
        />
        <!-- Below sm the reason takes its own line under the buttons, so a long one never
             squeezes the primary action off the panel; the idle hint is left out there. -->
        <span
          class="order-3 w-full text-p-sm sm:order-2 sm:block sm:w-auto sm:min-w-0 sm:flex-1 sm:text-end"
          :class="blockedReason ? 'text-ink-gray-7' : 'hidden text-ink-gray-5'"
        >
          {{ blockedReason || __('Nothing is saved until the last step.') }}
        </span>
      </div>
    </div>
  </Dialog>
</template>
