<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { refDebounced } from '@vueuse/core'
import { Button, MultiSelect } from 'frappe-ui'
import { useMethodRead } from '../../data/api'

const SEARCH_DEBOUNCE_MS = 300

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  max: { type: Number, default: 0 },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const query = ref('')
const searchText = refDebounced(query, SEARCH_DEBOUNCE_MS)

const results = useMethodRead('commera.api.storefront.products.get_products', {
  params: () => ({ query: searchText.value, page_size: 20 }),
  refetch: true,
})

const titles = reactive({})
watch(
  () => results.data,
  (page) => {
    for (const product of page?.products ?? []) titles[product.id] = product.title
  },
)

const options = computed(() => {
  const merged = new Map(
    (results.data?.products ?? []).map((product) => [product.id, { label: product.title, value: product.id }]),
  )
  for (const code of props.modelValue) {
    if (!merged.has(code)) merged.set(code, { label: titles[code] ?? code, value: code })
  }
  const full = props.max && props.modelValue.length >= props.max
  return [...merged.values()].map((option) => ({
    ...option,
    disabled: Boolean(full) && !props.modelValue.includes(option.value),
  }))
})

function update(codes) {
  emit('update:modelValue', props.max ? codes.slice(0, props.max) : codes)
}
</script>

<template>
  <div class="w-full sm:w-72">
    <MultiSelect
      v-model:query="query"
      class="w-full"
      :model-value="modelValue"
      :options="options"
      :loading="results.loading"
      :filterable="false"
      :disabled="disabled"
      placeholder="Pick products"
      @update:model-value="update"
    >
      <template #footer="{ clear }">
        <div v-if="modelValue.length" class="border-t border-outline-gray-1 px-2 py-1.5">
          <Button variant="ghost" size="sm" @click="clear">Clear All</Button>
        </div>
      </template>
    </MultiSelect>
  </div>
</template>
