<script setup>
import { Button, Skeleton } from 'frappe-ui'

defineProps({
  finishing: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
})
defineEmits(['finish'])
</script>

<template>
  <div class="space-y-6">
    <p class="flex items-start gap-2 text-p-base text-ink-gray-6">
      <span class="lucide-lock mt-0.5 size-4 shrink-0" aria-hidden="true" />
      Only you can see it for now. Publish it from Home when you are ready.
    </p>
    <Button
      v-if="isReady"
      variant="solid"
      size="md"
      class="w-full"
      label="Go to Home"
      :loading="finishing"
      @click="$emit('finish')"
    />
    <Skeleton v-else role="status" class="h-8 w-full rounded-4" aria-label="Finishing setup" />
  </div>
</template>
