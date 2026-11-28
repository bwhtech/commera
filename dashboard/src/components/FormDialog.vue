<script setup>
/**
 * A create or edit dialog whose footer never leaves the screen: a title (with an optional
 * description under it), a body that scrolls, and Cancel + one primary task verb. A disabled
 * primary names its reason on the same footer. From `sm` it is a centred dialog, below it a
 * bottom sheet (DialogShell). With `dirty`, every way of closing asks before typed work is lost.
 */
import { Button } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed } from 'vue'
import DialogShell from './DialogShell.vue'
import { __ } from '../data/translation'
import { confirmLeave } from '../utils/confirmLeave'
import { useIsMobile } from '../utils/useIsMobile'

const props = defineProps({
  title: { type: String, required: true },
  // One quiet line under the title, outside the scrolling body, such as "Color of Cotton tee".
  description: { type: String, default: '' },
  size: { type: String, default: 'xl' },
  primaryLabel: { type: String, required: true },
  primaryDisabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  // Why the primary is disabled; wins over `note`, which is a quiet line for when nothing is missing.
  reason: { type: String, default: '' },
  note: { type: String, default: '' },
  dismissible: { type: Boolean, default: true },
  // Something typed or picked that closing would throw away. A caller that closes the dialog
  // itself after a save sets `open` directly, which is never guarded.
  dirty: { type: Boolean, default: false },
})

const open = defineModel('open', { type: Boolean, required: true })
const emit = defineEmits(['submit'])

const isMobile = useIsMobile()

// From `sm`, Escape and a click outside still ask to close, and the ask is answered below. A
// sheet's swipe cannot be asked: frappe-ui flings the sheet off screen before it reports the
// dismissal. So a dirty sheet turns its swipe and outside tap off and leaves Cancel, which asks.
const shellDismissible = computed(
  () => props.dismissible && !props.loading && !(isMobile.value && props.dirty),
)

async function requestClose() {
  if (props.loading) return
  if (
    props.dirty &&
    !(await confirmLeave(__('Discard changes?'), __('What you entered here is not saved.'), __('Discard')))
  ) {
    return
  }
  open.value = false
}

function onOpenChange(value) {
  if (value) open.value = true
  else requestClose()
}
</script>

<template>
  <DialogShell
    :open="open"
    :title="props.title"
    :size="props.size"
    :dismissible="shellDismissible"
    :close-disabled="!props.dismissible || props.loading"
    focus-body
    @update:open="onOpenChange"
  >
    <template v-if="props.description" #header>
      <!-- reka's DialogDescription carries the id the dialog's aria-describedby points at. -->
      <DialogDescription class="mt-1 text-pretty text-p-sm text-ink-gray-6">{{ props.description }}</DialogDescription>
    </template>

    <slot />

    <template #footer="{ buttonSize }">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <!-- With no header description, the footer line describes the dialog. It stays in the DOM
             (hidden when empty) so aria-describedby never points at a missing element. -->
        <component
          :is="props.description ? 'p' : DialogDescription"
          class="min-w-0 flex-1 text-p-sm"
          :class="[props.reason ? 'text-ink-gray-7' : 'text-ink-gray-6', { hidden: !props.reason && !props.note }]"
          aria-live="polite"
        >
          {{ props.reason || props.note }}
        </component>
        <!-- Two equal halves on a phone, so both answers are thumb-sized; content width from `sm`. -->
        <div class="grid grid-cols-2 gap-2 sm:ms-auto sm:flex sm:items-center">
          <Button :size="buttonSize" :label="__('Cancel')" :disabled="props.loading" @click="requestClose" />
          <Button
            :size="buttonSize"
            variant="solid"
            theme="gray"
            :label="props.primaryLabel"
            :disabled="props.primaryDisabled"
            :loading="props.loading"
            @click="emit('submit')"
          />
        </div>
      </div>
    </template>
  </DialogShell>
</template>
