<script setup>
import { Button } from 'frappe-ui'

defineProps({
  controls: { type: String, required: true },
  collapsed: { type: Boolean, default: false },
  label: { type: String, required: true },
})

const emit = defineEmits(['toggle'])
</script>

<template>
  <div data-slot="sidebar-edge" class="group relative z-10 shrink-0 border-e border-outline-gray-1">
    <div class="absolute inset-y-0 -start-1 -end-1 cursor-pointer" aria-hidden="true" @click="emit('toggle')" />
    <Button
      variant="outline"
      size="xs"
      class="absolute bottom-4 start-0 -translate-x-1/2 rtl:translate-x-1/2 rtl:-scale-x-100 !rounded-full bg-surface-base opacity-0 shadow-sm transition-opacity duration-200 focus-visible:opacity-100 group-hover:opacity-100 motion-reduce:transition-none"
      :icon="collapsed ? 'lucide-chevron-right' : 'lucide-chevron-left'"
      :aria-label="collapsed ? __('Expand {0}', [label]) : __('Collapse {0}', [label])"
      :aria-expanded="!collapsed"
      :aria-controls="controls"
      @click="emit('toggle')"
    />
  </div>
</template>
