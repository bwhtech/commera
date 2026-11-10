<script setup>
/**
 * Every report wears the same header: a range and a compare toggle. The
 * sameness is the point. A report answers a question, so it carries no
 * primary action, which is what keeps it from reading like the dashboard.
 */
import { computed } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import { __ } from '../data/translation'
import AppPageHeader from './AppPageHeader.vue'
import ResponsiveButton from './ResponsiveButton.vue'

const props = defineProps({
  title: { type: String, required: true },
  range: { type: String, required: true },
  compare: { type: Boolean, default: false },
})

const emit = defineEmits(['update:range', 'update:compare'])

const RANGES = [
  { value: 'Last 7 days', label: __('Last 7 days') },
  { value: 'Last 30 days', label: __('Last 30 days') },
  { value: 'Last 12 months', label: __('Last 12 months') },
  { value: 'All time', label: __('All time') },
]

const rangeLabel = computed(() => RANGES.find((option) => option.value === props.range)?.label ?? props.range)
</script>

<template>
  <!-- No `back-to`: this header is shared by all three reports and knows none of
       their origins, so any fixed target is a wrong arrow. The Analytics
       breadcrumb on the same line is the real way up. -->
  <AppPageHeader
    :title="title"
    :breadcrumbs="[{ label: __('Analytics'), route: '/analytics/revenue' }, { label: title }]"
  >
    <template #actions>
      <Dropdown :options="RANGES.map(({ value, label }) => ({ label, onClick: () => emit('update:range', value) }))">
        <Button :label="rangeLabel" icon-right="lucide-chevron-down" />
      </Dropdown>
      <!-- Two labelled actions plus the range starve the title on a phone, so
           Compare drops to its icon down there. -->
      <ResponsiveButton
        :label="__('Compare')"
        icon="lucide-git-compare"
        :variant="compare ? 'subtle' : 'ghost'"
        @click="emit('update:compare', !compare)"
      />
    </template>
  </AppPageHeader>
</template>

