<script setup>
import { ref, watch } from 'vue'
import { MultiSelect } from 'frappe-ui'
import { searchTargets } from '../../data/discounts'

// A discount's targets are rows of { role, target_type, target }; this picker owns the rows
// of one role and one type, and leaves every other row alone.
const targets = defineModel({ type: Array, required: true })
const props = defineProps({
  role: { type: String, required: true },
  targetType: { type: String, required: true },
  placeholder: { type: String, default: 'Search' },
})

const query = ref('')
const options = ref([])

function ownsRow(row) {
  return row.role === props.role && row.target_type === props.targetType
}

const selected = ref(targets.value.filter(ownsRow).map((row) => row.target))

watch(selected, (values) => {
  targets.value = [
    ...targets.value.filter((row) => !ownsRow(row)),
    ...values.map((target) => ({ role: props.role, target_type: props.targetType, target })),
  ]
})

// The server ranks and filters, so the options carry the chosen values too: without them a
// chosen product off the current search shows its raw code instead of its name.
watch(
  [query, () => props.targetType],
  async () => {
    const found = (await searchTargets(props.targetType, query.value)) ?? []
    const known = new Set(found.map((option) => option.value))
    options.value = [...found, ...selected.value.filter((value) => !known.has(value)).map((value) => ({ label: value, value }))]
  },
  { immediate: true },
)
</script>

<template>
  <MultiSelect v-model="selected" v-model:query="query" :options="options" :filterable="false" :placeholder="placeholder" />
</template>
