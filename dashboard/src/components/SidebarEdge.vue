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
  <div data-slot="sidebar-edge" class="group relative z-10 shrink-0 border-r border-outline-gray-1">
    <div class="absolute inset-y-0 -left-1 -right-1 cursor-pointer" aria-hidden="true" @click="emit('toggle')" />
    <Button
      variant="outline"
      size="xs"
      class="absolute bottom-4 left-0 -translate-x-1/2 !rounded-full bg-surface-base opacity-0 shadow-sm transition-opacity duration-200 focus-visible:opacity-100 group-hover:opacity-100 motion-reduce:transition-none"
      :icon="collapsed ? 'lucide-chevron-right' : 'lucide-chevron-left'"
      :aria-label="`${collapsed ? 'Expand' : 'Collapse'} ${label}`"
      :aria-expanded="!collapsed"
      :aria-controls="controls"
      @click="emit('toggle')"
    />
  </div>
</template>
