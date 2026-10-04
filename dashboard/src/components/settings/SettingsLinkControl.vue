<script setup>
/**
 * A Link docfield, searched on the server: the endpoint decides what matches, and it refuses any
 * doctype the settings doctype does not actually link to.
 */
import { computed } from 'vue'
import { Combobox } from 'frappe-ui'
import { useLinkSearch } from '../../data/linkSearch'

const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: String, default: '' },
  optionsPath: { type: String, required: true },
  // Only for a control inside a form; a settings row already names its control.
  label: { type: String, default: '' },
  required: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const search = useLinkSearch(
  props.optionsPath,
  () => ({ doctype: props.field.options }),
  () => props.modelValue,
)

// A search returns only what matches the query, so the stored value is merged in or it vanishes
// from the list as soon as someone types.
const options = computed(() => {
  const merged = new Map((search.results.data ?? []).map((option) => [option.value, option]))
  if (props.modelValue && !merged.has(props.modelValue)) {
    merged.set(props.modelValue, { label: props.modelValue, value: props.modelValue })
  }
  return [...merged.values()]
})
</script>

<template>
  <div class="w-full sm:w-72">
    <Combobox
      v-model:open="search.open.value"
      v-model:query="search.query.value"
      :model-value="modelValue"
      :options="options"
      :label="label || undefined"
      :required="required"
      :filterable="false"
      :loading="search.results.loading"
      :placeholder="`Search ${field.options}`"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>
