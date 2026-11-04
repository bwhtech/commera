<script setup>
import { computed } from 'vue'
import { Combobox } from 'frappe-ui'
import { useMethodRead } from '../../data/api'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const collections = useMethodRead('commera.api.storefront.collections.get_collections')

const options = computed(() => {
  const merged = new Map(
    (collections.data ?? []).map((collection) => [
      collection.handle,
      { label: collection.title, value: collection.handle },
    ]),
  )
  if (props.modelValue && !merged.has(props.modelValue)) {
    merged.set(props.modelValue, { label: props.modelValue, value: props.modelValue })
  }
  return [...merged.values()]
})
</script>

<template>
  <div class="w-full sm:w-72">
    <Combobox
      class="w-full"
      :model-value="modelValue"
      :options="options"
      :loading="collections.loading"
      :disabled="disabled"
      placeholder="Pick a collection"
      @update:model-value="emit('update:modelValue', $event ?? '')"
    />
  </div>
</template>
