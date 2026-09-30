<script setup>
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { isPriced, rateSummary } from '../../data/shippingRates'

const props = defineProps({
  title: { type: String, required: true },
  // Null for the bands that name no delivery option.
  option: { type: Object, default: null },
  bands: { type: Array, default: () => [] },
  formatBoundary: { type: Function, required: true },
})

defineEmits(['edit'])

const summary = computed(() => rateSummary(props.bands, props.option, props.formatBoundary))
const hidden = computed(() => Boolean(props.option) && !isPriced(props.bands, props.option))
const muted = computed(() => Boolean(props.option) && !props.option.enabled)
</script>

<template>
  <div class="flex items-center gap-3 py-3">
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate text-base" :class="muted ? 'text-ink-gray-5' : 'text-ink-gray-8'">
          {{ title }}
        </p>
        <Badge v-if="muted" label="Off" theme="gray" variant="subtle" />
        <Badge v-else-if="hidden" label="Hidden at checkout" theme="gray" variant="subtle" />
      </div>
      <p v-if="summary" class="mt-1 truncate text-sm text-ink-gray-5">{{ summary }}</p>
    </div>

    <Button
      class="shrink-0"
      :label="bands.length ? 'Edit rates' : 'Set rates'"
      @click="$emit('edit')"
    />
  </div>
</template>
