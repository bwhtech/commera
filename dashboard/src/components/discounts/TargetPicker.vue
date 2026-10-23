<script setup>
import { computed } from 'vue'
import SearchMultiSelect from './SearchMultiSelect.vue'

// Owns rows of one role and type; leaves every other row alone.
const targets = defineModel({ type: Array, required: true })
const props = defineProps({
  role: { type: String, required: true },
  targetType: { type: String, required: true },
  label: { type: String, required: true },
  placeholder: { type: String, default: 'Search' },
})

const ownsRow = (row) => row.role === props.role && row.target_type === props.targetType

const selected = computed({
  get: () => targets.value.filter(ownsRow).map((row) => row.target),
  set: (values) => {
    targets.value = [
      ...targets.value.filter((row) => !ownsRow(row)),
      ...values.map((target) => ({ role: props.role, target_type: props.targetType, target })),
    ]
  },
})
</script>

<template>
  <SearchMultiSelect v-model="selected" :target-type="targetType" :label="label" :placeholder="placeholder" />
</template>
