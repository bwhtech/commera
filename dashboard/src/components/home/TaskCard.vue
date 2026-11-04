<script setup>
import { Badge, Button, Tooltip } from 'frappe-ui'
import TaskArt from './TaskArt.vue'

defineProps({
  task: { type: Object, required: true },
  store: { type: Object, required: true },
})
defineEmits(['dismiss'])
</script>

<template>
  <div class="group relative flex flex-col rounded-6 border border-outline-gray-1 bg-surface-base p-2 shadow-sm">
    <TaskArt :kind="task.key" :store="store" />
    <Tooltip text="Dismiss card">
      <Button
        icon="lucide-x"
        size="sm"
        variant="subtle"
        aria-label="Dismiss card"
        class="absolute right-4 top-4 rounded-full transition-opacity duration-150 can-hover:opacity-0 can-hover:group-focus-within:opacity-100 group-hover:opacity-100"
        @click="$emit('dismiss')"
      />
    </Tooltip>
    <div class="flex flex-1 flex-col px-2.5 pb-2.5 pt-3.5">
      <div class="flex flex-wrap items-center gap-2">
        <h3 class="text-lg-semibold text-ink-gray-9">{{ task.title }}</h3>
        <Badge v-if="task.required" label="Needed to sell" theme="amber" variant="subtle" size="sm" />
      </div>
      <p class="mt-1.5 text-p-sm text-ink-gray-6">{{ task.description }}</p>
      <div class="mt-auto pt-5">
        <Button :label="task.action" :route="task.route" />
      </div>
    </div>
  </div>
</template>
