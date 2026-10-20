<script setup>
import { computed, ref } from 'vue'
import { Combobox } from 'frappe-ui'
import { refDebounced } from '@vueuse/core'
import { useAdminRead } from '../../data/api'

const model = defineModel({ type: String, default: null })
const props = defineProps({
  targetType: { type: String, required: true },
  placeholder: { type: String, default: 'Search' },
})

// Its own request, not the module's shared caller: two pickers searching at once would abort each other.
const query = ref('')
const search = refDebounced(query, 300)
const results = useAdminRead('discounts.search_targets', {
  params: () => ({ target_type: props.targetType, search: search.value, sellable: 1 }),
  refetch: true,
})

// A search returns only what matches, so the chosen option is kept or its name vanishes once someone types.
const chosen = ref(null)
const options = computed(() => {
  const found = results.data ?? []
  return chosen.value && !found.some((option) => option.value === chosen.value.value) ? [chosen.value, ...found] : found
})

function pick(value) {
  chosen.value = options.value.find((option) => option.value === value) ?? null
  model.value = value
}
</script>

<template>
  <Combobox
    v-model:query="query"
    :model-value="model"
    :options="options"
    :filterable="false"
    :loading="results.loading"
    :placeholder="placeholder"
    @update:model-value="pick"
  />
</template>
