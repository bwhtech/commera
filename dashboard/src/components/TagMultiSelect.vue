<script setup>
/**
 * frappe-ui MultiSelect that shows each pick as a removable tag, after the "Issue labels" example in
 * the MultiSelect docs. Label, description, error and options pass straight through to MultiSelect.
 * There is no Select All: a tag picker files one thing under each pick.
 */
import { Badge, MultiSelect } from 'frappe-ui'
import { __ } from '../data/translation'

const props = defineProps({
  placeholder: { type: String, default: () => __('Add…') },
  disabled: { type: Boolean, default: false },
  // (option, index) => icon class or null, shown before a tag's label.
  tagIcon: { type: Function, default: null },
})

const selected = defineModel({ type: Array, default: () => [] })

function remove(value) {
  selected.value = selected.value.filter((picked) => picked !== value)
}
</script>

<template>
  <MultiSelect v-model="selected" :disabled="props.disabled">
    <!-- MultiSelect's anchor already toggles the popover on click, so the trigger has no click handler. -->
    <template #trigger="{ open, selectedOptions }">
      <button
        type="button"
        :disabled="props.disabled"
        :data-state="open ? 'open' : 'closed'"
        class="relative flex min-h-7 w-full items-center gap-2 rounded-4 border py-1 pl-1 pr-2 text-left text-base transition-[background-color,border-color,box-shadow] duration-150 data-[state=open]:focus-ring"
        :class="
          props.disabled
            ? 'cursor-not-allowed border-transparent bg-surface-gray-1 text-ink-gray-4'
            : 'border-[--surface-gray-2] bg-surface-gray-2 text-ink-gray-7 hover:border-outline-elevation-2 hover:bg-surface-gray-3'
        "
      >
        <span class="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          <Badge
            v-for="(option, index) in selectedOptions"
            :key="option.value"
            size="md"
            variant="outline"
            class="max-w-full bg-surface-base"
          >
            <template v-if="props.tagIcon?.(option, index)" #prefix>
              <span :class="[props.tagIcon(option, index), 'size-3']" />
            </template>
            <span class="truncate">{{ option.label }}</span>
            <template v-if="!props.disabled" #suffix>
              <span
                role="button"
                tabindex="-1"
                :aria-label="__('Remove {0}', [option.label])"
                class="-mr-0.5 inline-flex cursor-pointer items-center justify-center rounded-1 p-0.5 opacity-70 hover:opacity-100"
                @click.stop="remove(option.value)"
                @pointerdown.stop
              >
                <span class="lucide-x size-3" />
              </span>
            </template>
          </Badge>
          <span v-if="!selectedOptions.length" class="px-1 text-ink-gray-4">{{ props.placeholder }}</span>
        </span>
        <span
          :class="['lucide-chevron-down size-4 shrink-0 text-ink-gray-4 transition-transform', open && 'rotate-180']"
        />
      </button>
    </template>
    <template #footer />
  </MultiSelect>
</template>
