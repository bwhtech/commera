<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Spinner, toast } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { canChangeStep, closeImport, imp, isMappingChecked, steps } from '../../data/importFlow'
import { loadErpnextPreview } from '../../data/erpnextImport'
import { erpnextImportLabel, importLabel } from '../../data/importCounts'
import { fieldLabel, stillNeeded } from '../../data/importMapping'
import DialogShell from '../DialogShell.vue'
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
const shell = ref(null)
watch(
  () => imp.step,
  () => shell.value?.scrollToTop(),
)
const stepKey = computed(() => steps.value[imp.step]?.key)

// "Step 2 of 5 · Match columns". The source step has no total and no step bar: picking ERPNext or a
// spreadsheet decides how many steps follow, and a total that jumps from 6 to 3 reads like a mistake.
const isSourceStep = computed(() => stepKey.value === 'source')
const stepLine = computed(() => {
  if (!isReady.value) return __('Loading…')
  if (imp.phase === 'running') return __('Import running…')
  const label = steps.value[imp.step]?.label
  if (isSourceStep.value) return __('Step 1 · {0}', [label])
  return __('Step {0} of {1} · {2}', [imp.step + 1, steps.value.length, label])
})
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
  if (stepKey.value === 'review' && !imp.counts.ready) return __('Fix the skipped rows in your file to import.')
  if (stepKey.value === 'pick' && !imp.erpnext.selectionReady) return __('Loading your items…')
  if (stepKey.value === 'pick' && !erpnextSelected.value) return __('Pick at least one item.')
  return ''
})

const canContinue = computed(() => canChangeStep.value && !blockedReason.value)

const nextLabel = computed(() => {
  // With no row ready there is nothing to add photos to, so there is nothing to skip either.
  if (stepKey.value === 'images') return assignedPhotos.value || !imp.counts.ready ? __('Continue') : __('Skip photos')
  if (stepKey.value === 'review') return importLabel(imp.counts)
  if (stepKey.value === 'pick') return erpnextImportLabel(erpnextSelected.value)
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
  <!-- Never dismissible: Escape or a stray click would throw away a mapped file. The × (in the
       sheet's corner on a phone, whose footer has no Cancel) is the way out. -->
  <DialogShell
    ref="shell"
    :open="imp.open"
    :title="__('Import products')"
    size="5xl"
    position="top"
    :dismissible="false"
    close-button="always"
    @update:open="(open) => (open ? null : close())"
  >
    <!-- The step line and the step bar stay put above the body, like FormDialog's description. -->
    <template #header>
      <DialogDescription class="mt-1 text-p-sm text-ink-gray-6">{{ stepLine }}</DialogDescription>
      <div v-if="isReady && !isSourceStep" class="mt-4">
        <ImportStepNav />
      </div>
    </template>

    <div class="sm:pt-2">
      <component :is="current" v-if="isReady" @next="next" />
      <div v-else class="flex justify-center py-14"><Spinner class="size-5" /></div>
    </div>

    <!-- FormDialog's footer: the reason (or, from sm, the idle hint) on the left, Back + the primary on the right. -->
    <template v-if="isReady && !onLastStep" #footer="{ buttonSize }">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <p
          class="min-w-0 flex-1 text-p-sm"
          :class="blockedReason ? 'text-ink-gray-7' : 'text-ink-gray-6 max-sm:hidden'"
          aria-live="polite"
        >
          {{ blockedReason || __('Nothing is saved until the last step.') }}
        </p>
        <!-- A phone fills the width. Back and Continue split it; the import button, whose label
             carries the counts ("Import 2 products (3 variants)"), takes all but Back's own width
             so the counts are never cut. -->
        <div class="flex gap-2 sm:ms-auto sm:items-center">
          <Button
            v-if="imp.step > 0"
            :class="startsImport ? 'shrink-0' : 'max-sm:flex-1'"
            :size="buttonSize"
            icon-left="lucide-arrow-left rtl:-scale-x-100"
            :label="__('Back')"
            :disabled="!canChangeStep"
            @click="back"
          />
          <Button
            class="max-sm:min-w-0 max-sm:flex-1"
            :size="buttonSize"
            variant="solid"
            theme="gray"
            :disabled="!canContinue"
            :label="nextLabel"
            :icon-right="startsImport ? undefined : 'lucide-arrow-right rtl:-scale-x-100'"
            @click="next"
          />
        </div>
      </div>
    </template>
  </DialogShell>
</template>
