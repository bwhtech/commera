<script setup>
/**
 * Pick attribute values (colors, sizes) from the ones this store already uses, or type
 * one it does not have yet and add it from the list's footer — catalog.create_product
 * appends anything new to the Item Attribute on the way in.
 */
import { computed, ref, watch } from 'vue'
import { Button, MultiSelect } from 'frappe-ui'
import SwatchDot from './SwatchDot.vue'
import { useAdminRead } from '../data/api'

const props = defineProps({
  attribute: { type: String, required: true },
  label: { type: String, required: true },
  placeholder: { type: String, default: '' },
  description: { type: String, default: '' },
  required: { type: Boolean, default: false },
})

const selected = defineModel({ type: Array, required: true })

// Surfaced so the host dialog can stand down from outside-dismissal while this popover owns the click.
const open = defineModel('open', { type: Boolean, default: false })

const emit = defineEmits(['values'])

const valuesRequest = useAdminRead('catalog.get_attribute_values', {
  params: () => ({ attribute: props.attribute }),
  refetch: true,
})

watch(
  () => valuesRequest.data,
  (values) => emit('values', values ?? []),
)

// A value the owner types lives only in this picker until the product is created, so it is held here.
const addedValues = ref([])
const query = ref('')

watch(
  () => props.attribute,
  () => {
    addedValues.value = []
  },
)

const options = computed(() => [
  ...(valuesRequest.data ?? []).map((entry) => ({
    label: entry.value,
    value: entry.value,
    color: entry.color,
    image: entry.image,
  })),
  ...addedValues.value.map((value) => ({ label: value, value })),
])

// ERPNext matches attribute values case-insensitively, so "red" beside "Red" would add nothing new.
function canAdd(query) {
  const typed = query.trim()
  return Boolean(typed) && !options.value.some((option) => option.value.toLowerCase() === typed.toLowerCase())
}

function addTypedValue() {
  const typed = query.value.trim()
  addedValues.value.push(typed)
  selected.value = [...selected.value, typed]
  query.value = ''
}
</script>

<template>
  <MultiSelect
    v-model="selected"
    v-model:open="open"
    v-model:query="query"
    :label="props.label"
    :placeholder="props.placeholder"
    :description="props.description"
    :required="props.required"
    :options="options"
    :loading="valuesRequest.loading"
  >
    <template #summary="{ summary, selectedOptions }">
      {{ selectedOptions.length ? selectedOptions.map((option) => option.label).join(', ') : summary }}
    </template>
    <template #item-prefix="{ item }">
      <SwatchDot v-if="item.color || item.image" :color="item.color" :image="item.image" size="sm" />
    </template>
    <!-- Replaces frappe-ui's Clear All / Select All row: a size list is picked, never bulk-selected. -->
    <template #footer="{ clear }">
      <div v-if="canAdd(query) || selected.length" class="border-t border-outline-gray-1 p-1.5">
        <Button
          v-if="canAdd(query)"
          class="w-full justify-start"
          variant="ghost"
          icon-left="lucide-plus"
          :label="__('Add “{0}”', [query.trim()])"
          @click="addTypedValue"
        />
        <Button v-else variant="ghost" size="sm" :label="__('Clear')" @click="clear" />
      </div>
    </template>
  </MultiSelect>
</template>

