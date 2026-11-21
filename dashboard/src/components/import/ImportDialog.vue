<script setup>
import { computed } from 'vue'
import { Badge, Button, Dialog, toast } from 'frappe-ui'
import { REQUIRED_FIELDS, canChangeStep, closeImport, imp, steps } from '../../data/importFlow'
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
const stepKey = computed(() => steps.value[imp.step].key)
const current = computed(() => stepComponents[imp.source][stepKey.value])

const erpnextSelected = computed(() => imp.erpnext.selected.length)

const canContinue = computed(() => {
  if (!canChangeStep.value) return false
  if (stepKey.value === 'upload') return imp.parsed
  if (stepKey.value === 'map') return REQUIRED_FIELDS.every((f) => Object.values(imp.mapping).includes(f))
  // run_import with nothing ready writes nothing and still reads as "0 products are live".
  if (stepKey.value === 'review') return imp.counts.ready > 0
  if (stepKey.value === 'pick') return imp.erpnext.selectionReady && erpnextSelected.value > 0
  return true
})

const assignedPhotos = computed(() =>
  Object.values(imp.imageAssignments).reduce((total, fileUrls) => total + fileUrls.length, 0),
)

const nextLabel = computed(() => {
  if (stepKey.value === 'images') return assignedPhotos.value ? __('Continue') : __('Skip photos for now')
  if (stepKey.value === 'review') return imp.counts.ready === 1 ? __('Import 1 product') : __('Import {0} products', [imp.counts.ready])
  if (stepKey.value === 'pick') return erpnextSelected.value === 1 ? __('Import 1 item') : __('Import {0} items', [erpnextSelected.value])
  return __('Continue')
})

const startsImport = computed(() => stepKey.value === 'review' || stepKey.value === 'pick')

const onLastStep = computed(() => imp.step === steps.value.length - 1)

function next() {
  if (canChangeStep.value && imp.step < steps.value.length - 1) imp.step += 1
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
      <div class="flex items-center gap-3 border-b border-outline-gray-1 px-6 py-4">
        <span class="text-lg-semibold text-ink-gray-9">{{ __('Import products') }}</span>
        <Badge
          :label="imp.phase === 'done' ? __('Done') : __('Step {0} of {1}', [imp.step + 1, steps.length])"
          :theme="imp.phase === 'done' ? 'green' : 'gray'"
          variant="subtle"
        />
        <div class="ms-auto flex items-center gap-2">
          <span v-if="imp.phase === 'running'" class="text-sm text-ink-gray-5">{{ __('Import running…') }}</span>
          <Button variant="ghost" icon="lucide-x" :label="__('Close')" @click="close" />
        </div>
      </div>

      <div class="border-b border-outline-gray-1 px-6 py-4">
        <ImportStepNav />
      </div>

      <div v-scroll-fade class="min-h-0 flex-1 overflow-y-auto px-6 py-7">
        <component :is="current" @next="next" />
      </div>

      <!-- Nothing is committed until the last step, so the footer says so. -->
      <div
        v-if="!onLastStep"
        class="flex items-center gap-3 border-t border-outline-gray-1 bg-surface-gray-1 px-6 py-4"
      >
        <Button
          v-if="imp.step > 0"
          icon-left="lucide-arrow-left rtl:-scale-x-100"
          :label="__('Back')"
          :disabled="!canChangeStep"
          @click="back"
        />
        <span class="hidden text-sm text-ink-gray-5 sm:block">{{ __('Nothing is saved until the last step.') }}</span>
        <div class="ms-auto flex items-center gap-2">
          <Button v-if="stepKey === 'images'" variant="ghost" :label="__('Do this later')" :disabled="!canChangeStep" @click="next" />
          <Button
            variant="solid"
            theme="gray"
            :disabled="!canContinue"
            :label="nextLabel"
            :icon-right="startsImport ? 'lucide-rocket' : 'lucide-arrow-right rtl:-scale-x-100'"
            @click="next"
          />
        </div>
      </div>
    </div>
  </Dialog>
</template>

