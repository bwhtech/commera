<script setup>
/**
 * A page of rows, and the way to the next one. Long lists are read in pages,
 * not scrolled to the end — and a count is the only way to know how much is
 * behind the screen you are on.
 */
import { computed } from 'vue'
import { Select } from 'frappe-ui'
import ResponsiveButton from './ResponsiveButton.vue'

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  total: { type: Number, required: true },
})

const emit = defineEmits(['update:page', 'update:pageSize'])

const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const first = computed(() => (props.total ? (props.page - 1) * props.pageSize + 1 : 0))
const last = computed(() => Math.min(props.page * props.pageSize, props.total))

function setSize(size) {
  emit('update:pageSize', Number(size))
  emit('update:page', 1)
}
</script>

<template>
  <div class="mt-3 flex flex-wrap items-center gap-3 border-t border-outline-gray-1 pt-3">
    <p class="text-sm text-ink-gray-5 tabular-nums">{{ __('{0}–{1} of {2}', [first, last, total]) }}</p>

    <div class="ms-auto flex items-center gap-2">
      <Select
        :model-value="String(pageSize)"
        :aria-label="__('Rows per page')"
        size="sm"
        class="w-32"
        :options="[
          { label: __('{0} per page', [10]), value: '10' },
          { label: __('{0} per page', [20]), value: '20' },
          { label: __('{0} per page', [50]), value: '50' },
        ]"
        @update:model-value="setSize"
      />
      <ResponsiveButton
        :label="__('Previous')"
        icon="lucide-chevron-left rtl:-scale-x-100"
        :disabled="page <= 1"
        @click="emit('update:page', page - 1)"
      />
      <ResponsiveButton
        :label="__('Next')"
        icon="lucide-chevron-right rtl:-scale-x-100"
        icon-position="right"
        :disabled="page >= pageCount"
        @click="emit('update:page', page + 1)"
      />
    </div>
  </div>
</template>
