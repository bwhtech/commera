<script setup>
import { Button, Skeleton } from 'frappe-ui'

defineProps({
  finishing: { type: Boolean, default: false },
  // The store setup's status: only `done` can finish, and a `failed` one is retried from the
  // alert above, so it must not read as a skeleton that will resolve on its own.
  setupStatus: { type: String, default: 'idle' },
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
      v-if="setupStatus === 'done'"
      variant="solid"
      size="md"
      class="w-full"
      label="Go to Home"
      :loading="finishing"
      @click="$emit('finish')"
    />
    <p v-else-if="setupStatus === 'failed'" class="text-p-base text-ink-red-6">
      Your store could not be set up. Retry it above, then come back here.
    </p>
    <Skeleton v-else role="status" class="h-8 w-full rounded-4" aria-label="Finishing setup" />
  </div>
</template>
