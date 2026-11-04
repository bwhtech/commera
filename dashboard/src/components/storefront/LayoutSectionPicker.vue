<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { acceptsSection } from '../../data/themeLayout'

const props = defineProps({
  schemas: { type: Array, required: true },
  group: { type: String, required: true },
})

const emit = defineEmits(['pick', 'back'])

const categories = computed(() => {
  const grouped = new Map()
  for (const schema of props.schemas) {
    if (!acceptsSection(schema, props.group)) continue
    const category = schema.category || 'Other'
    if (!grouped.has(category)) grouped.set(category, [])
    grouped.get(category).push(schema)
  }
  return [...grouped.entries()].map(([label, schemas]) => ({ label, schemas }))
})
</script>

<template>
  <div class="flex flex-col gap-3" data-section-picker>
    <div class="flex items-center gap-1">
      <Button variant="ghost" icon="lucide-arrow-left" aria-label="Back to sections" @click="emit('back')" />
      <h2 class="text-base font-medium text-ink-gray-9">Add section</h2>
    </div>

    <div v-for="category in categories" :key="category.label">
      <p class="px-2 text-sm text-ink-gray-5">{{ category.label }}</p>
      <div class="mt-1 flex flex-col">
        <button
          v-for="schema in category.schemas"
          :key="schema.type"
          type="button"
          class="flex items-center gap-2 rounded-4 px-2 py-1.5 text-start text-base text-ink-gray-8 hover:bg-surface-gray-2"
          :data-section-type="schema.type"
          @click="emit('pick', schema.type)"
        >
          <span class="lucide-layout-template size-4 text-ink-gray-5" aria-hidden="true" />
          {{ schema.name ?? schema.type }}
        </button>
      </div>
    </div>
  </div>
</template>
