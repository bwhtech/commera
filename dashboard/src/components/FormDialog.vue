<script setup>
/**
 * A create or edit dialog whose footer never leaves the screen: a title row (with an optional
 * description under it), a body that scrolls, and Cancel + one primary task verb. A disabled
 * primary names its reason on the same footer.
 */
import { Button, Dialog } from 'frappe-ui'
import { DialogDescription, DialogTitle } from 'reka-ui'

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
})

const open = defineModel('open', { type: Boolean, required: true })
const emit = defineEmits(['submit'])
</script>

<template>
  <Dialog v-model:open="open" :size="props.size" bare :dismissible="props.dismissible && !props.loading">
    <!-- The panel fits the window with its footer visible: Dialog's own frame (py-4 + my-8) takes
         6rem and the body scrolls in the rest. dvh, not vh: on a phone vh is the height with the
         address bar hidden, which would push the footer off. -->
    <div class="flex max-h-[calc(100dvh-6rem)] flex-col">
      <div class="flex items-start gap-3 px-4 pb-4 pt-5 sm:px-6">
        <div class="min-w-0 flex-1">
          <!-- reka's primitives carry the ids the dialog's aria-labelledby / aria-describedby point at. -->
          <DialogTitle class="text-2xl-semibold text-ink-gray-8">{{ props.title }}</DialogTitle>
          <DialogDescription v-if="props.description" class="mt-1 text-p-sm text-ink-gray-5">
            {{ props.description }}
          </DialogDescription>
        </div>
        <Button
          class="-mt-0.5"
          variant="ghost"
          icon="lucide-x"
          :aria-label="__('Close')"
          :disabled="!props.dismissible || props.loading"
          @click="open = false"
        />
      </div>

      <div v-scroll-fade class="min-h-0 flex-1 overflow-y-auto px-4 pb-6 sm:px-6">
        <slot />
      </div>

      <div
        class="flex flex-col gap-3 border-t border-outline-gray-1 px-4 py-4 sm:flex-row sm:items-center sm:px-6"
      >
        <!-- With no header description, the footer line describes the dialog. It stays in the DOM
             (hidden when empty) so aria-describedby never points at a missing element. -->
        <component
          :is="props.description ? 'p' : DialogDescription"
          class="min-w-0 flex-1 text-p-sm"
          :class="[props.reason ? 'text-ink-gray-7' : 'text-ink-gray-5', { hidden: !props.reason && !props.note }]"
          aria-live="polite"
        >
          {{ props.reason || props.note }}
        </component>
        <div class="flex items-center justify-end gap-2 sm:ms-auto">
          <Button :label="__('Cancel')" :disabled="props.loading" @click="open = false" />
          <Button
            variant="solid"
            theme="gray"
            :label="props.primaryLabel"
            :disabled="props.primaryDisabled"
            :loading="props.loading"
            @click="emit('submit')"
          />
        </div>
      </div>
    </div>
  </Dialog>
</template>
