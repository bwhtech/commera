<script setup>
/**
 * A value in a list stays a value: plain text, aligned, readable down the
 * column. Setting it is a separate act, so the input only exists inside the
 * popover you opened on purpose.
 */
import { nextTick, ref, watch } from 'vue'
import { Button, FormControl, Popover } from 'frappe-ui'
import { money, symbolFor } from '../data/format'

const props = defineProps({
  modelValue: { type: Number, required: true },
  label: { type: String, required: true },
  format: { type: String, default: 'number' },
  description: { type: String, default: undefined },
  // No popover, no pencil — for a value commera has nothing to write to yet
  // (see callers for why), shown as the same tabular-nums text either way.
  readonly: { type: Boolean, default: false },
  emptyLabel: { type: String, default: undefined },
  // The trigger's accessible name; its visible text is only the value, such as "₹899".
  triggerLabel: { type: String, default: undefined },
  // Writes the value and resolves to '' once it is saved, or to the reason it was refused. With it
  // the popover stays open on a refusal, showing the reason under the input with the typed value
  // kept, and closes only on success. Without it the value is emitted and the popover closes.
  submit: { type: Function, default: undefined },
  // `end` for a number column read down its right edge: the hover pencil then sits before the
  // value, in the column's empty start side, so it never pushes the value off that edge.
  align: { type: String, default: 'start' },
})

const emit = defineEmits(['update:modelValue'])

const currency = symbolFor()
const draft = ref(props.modelValue)
const error = ref('')
const saving = ref(false)
const field = ref(null)
watch(() => props.modelValue, (value) => (draft.value = value))

// Every opening starts from the stored value: a refused value left behind by an outside click is
// not what the seller expects to find the next time.
function reset() {
  draft.value = props.modelValue
  error.value = ''
}

function focusInput() {
  field.value?.querySelector('input')?.focus()
}

async function save(close) {
  if (saving.value) return
  const value = Math.max(0, Number(draft.value) || 0)
  if (!props.submit) {
    emit('update:modelValue', value)
    close()
    return
  }
  saving.value = true
  try {
    error.value = (await props.submit(value)) || ''
  } finally {
    saving.value = false
  }
  if (!error.value) return close()
  // Save takes focus when it is clicked; the seller's next move is to retype, so it goes back.
  await nextTick()
  focusInput()
}

function cancel(close) {
  reset()
  close()
}
</script>

<template>
  <span v-if="readonly" class="px-1.5 py-0.5 text-base tabular-nums">
    {{ format === 'money' ? money(modelValue) : modelValue }}
  </span>

  <!-- The panel opens from the trigger's aligned edge: in an end-aligned column it grows back into
       the row instead of past the card's edge. -->
  <Popover v-else :align="align" :offset="4" @open="reset">
    <template #trigger="{ open }">
      <button
        class="group flex items-center gap-1 rounded-4 px-1.5 py-0.5 tabular-nums"
        :class="[
          open ? 'bg-surface-gray-3 text-ink-gray-8' : 'text-ink-gray-7 hover:bg-surface-gray-2',
          { 'flex-row-reverse': align === 'end' },
        ]"
        :aria-label="triggerLabel"
        @click.stop.prevent
      >
        <span v-if="emptyLabel && !modelValue" class="text-base text-ink-gray-6">{{ emptyLabel }}</span>
        <span v-else class="text-base">{{ format === 'money' ? money(modelValue) : modelValue }}</span>
        <span
          class="lucide-pencil size-3 text-ink-gray-6 transition-opacity"
          :class="open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100'"
          aria-hidden="true"
        />
      </button>
    </template>

    <template #default="{ close }">
      <div ref="field" class="w-56 space-y-3 p-1">
        <FormControl
          v-model="draft"
          type="number"
          inputmode="decimal"
          placeholder="0"
          :label="label"
          :description="description"
          :error="error || undefined"
          @keyup.enter="save(close)"
        >
          <template v-if="format === 'money'" #prefix>
            <span class="text-base text-ink-gray-6">{{ currency }}</span>
          </template>
        </FormControl>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" :disabled="saving" @click="cancel(close)" />
          <Button :label="__('Save')" variant="solid" theme="gray" :loading="saving" @click="save(close)" />
        </div>
      </div>
    </template>
  </Popover>
</template>
