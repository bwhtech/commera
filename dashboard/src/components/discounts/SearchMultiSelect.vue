<script setup>
import { computed } from 'vue'
import { MultiSelect } from 'frappe-ui'
import { useTargetSearch } from '../../data/discounts'

const selected = defineModel({ type: Array, required: true })
const props = defineProps({
  targetType: { type: String, required: true },
  label: { type: String, required: true },
  placeholder: { type: String, default: 'Search' },
  error: { type: String, default: null },
  knownLabels: { type: Object, default: () => ({}) },
})

const { query, results, labels, optionsWith } = useTargetSearch(() => props.targetType)
Object.assign(labels.value, props.knownLabels)

const options = computed(() => optionsWith(selected.value))
</script>

<template>
  <MultiSelect
    v-model="selected"
    v-model:query="query"
    :options="options"
    :filterable="false"
    :loading="results.loading"
    :label="label"
    :placeholder="placeholder"
    :error="error"
  />
</template>
