<script setup>
/**
 * A value in a list stays a value: plain text, aligned, readable down the
 * column. Setting it is a separate act, so the input only exists inside the
 * popover you opened on purpose.
 */
import { ref, watch } from 'vue'
import { Button, FormControl, Popover } from 'frappe-ui'
import { money } from '../data/format'

const props = defineProps({
  modelValue: { type: Number, required: true },
  label: { type: String, required: true },
  format: { type: String, default: 'number' },
  description: { type: String, default: undefined },
  // No popover, no pencil — for a value commera has nothing to write to yet
  // (see callers for why), shown as the same tabular-nums text either way.
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const draft = ref(props.modelValue)
watch(() => props.modelValue, (value) => (draft.value = value))

function save(close) {
  emit('update:modelValue', Math.max(0, Number(draft.value) || 0))
  close()
}

function cancel(close) {
  draft.value = props.modelValue
  close()
}
</script>

<template>
  <span v-if="readonly" class="px-1.5 py-0.5 text-base tabular-nums">
    {{ format === 'money' ? money(modelValue) : modelValue }}
  </span>

  <Popover v-else align="start" :offset="4">
    <template #trigger="{ open }">
      <button
        class="group flex items-center gap-1 rounded-4 px-1.5 py-0.5 tabular-nums"
        :class="open ? 'bg-surface-gray-3 text-ink-gray-8' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
        @click.stop.prevent
      >
        <span class="text-base">{{ format === 'money' ? money(modelValue) : modelValue }}</span>
        <span
          class="lucide-pencil size-3 text-ink-gray-4 transition-opacity"
          :class="open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
          aria-hidden="true"
        />
      </button>
    </template>

    <template #default="{ close }">
      <div class="w-56 space-y-3 p-1">
        <FormControl
          v-model="draft"
          type="number"
          :label="label"
          :description="description"
          @keyup.enter="save(close)"
        />
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="cancel(close)" />
          <Button :label="__('Save')" variant="solid" theme="gray" @click="save(close)" />
        </div>
      </div>
    </template>
  </Popover>
</template>

