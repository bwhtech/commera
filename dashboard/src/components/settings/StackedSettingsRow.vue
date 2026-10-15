<script setup>
import { onMounted, onUpdated, ref } from 'vue'
import { FormLabel } from 'frappe-ui'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: undefined },
  required: { type: Boolean, default: false },
})

// Same lookup as frappe-ui's SettingsRow: the controls generate their own ids, so the label finds it.
const CONTROL_SELECTOR = '[data-slot="control"], [role="combobox"], input, select, textarea'

const control = ref(null)
const controlId = ref(undefined)

function syncControlId() {
  controlId.value = control.value?.querySelector(CONTROL_SELECTOR)?.id || undefined
}

onMounted(syncControlId)
onUpdated(syncControlId)
</script>

<template>
  <div class="space-y-1.5 py-3.5">
    <FormLabel :id="controlId" :label="title" :required="required" size="md" />
    <div ref="control">
      <slot />
    </div>
    <p v-if="description" class="text-p-sm text-ink-gray-5">{{ description }}</p>
  </div>
</template>
