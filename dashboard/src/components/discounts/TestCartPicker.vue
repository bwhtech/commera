<script setup>
import { computed } from 'vue'
import { Combobox } from 'frappe-ui'
import { useTargetSearch } from '../../data/discounts'

const model = defineModel({ type: String, default: null })
const props = defineProps({
  targetType: { type: String, required: true },
  placeholder: { type: String, default: 'Search' },
})

const { query, results, optionsWith } = useTargetSearch(() => props.targetType, { sellable: true })
const options = computed(() => optionsWith([model.value]))
</script>

<template>
  <Combobox
    v-model="model"
    v-model:query="query"
    :options="options"
    :filterable="false"
    :loading="results.loading"
    :placeholder="placeholder"
  />
</template>
