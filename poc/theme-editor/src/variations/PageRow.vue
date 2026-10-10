<script setup>
import { Badge, Button } from 'frappe-ui'

// One row in a page list. `opens` is the plain-language hint under the
// action ("Opens Frappe Builder"), the only place the tool is named.
defineProps({
  icon: { type: String, required: true },
  title: { type: String, required: true },
  detail: { type: String, default: '' },
  status: { type: String, default: '' },
  action: { type: String, default: 'Edit' },
  external: { type: Boolean, default: false },
})
defineEmits(['edit'])
</script>

<template>
  <div class="flex items-center gap-4 px-4 py-3" :data-row="title">
    <span :class="icon" class="size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
    <div class="min-w-0 flex-1">
      <p class="truncate text-base font-medium text-ink-gray-9">{{ title }}</p>
      <p v-if="detail" class="truncate text-sm text-ink-gray-5">{{ detail }}</p>
    </div>
    <Badge v-if="status" :label="status" :theme="status === 'Published' ? 'green' : 'gray'" />
    <Button :label="action" :icon-right="external ? 'lucide-arrow-up-right' : undefined" @click="$emit('edit')" />
  </div>
</template>
