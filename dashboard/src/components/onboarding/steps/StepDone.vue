<script setup>
import { Button, toast } from 'frappe-ui'

defineProps({
  finishing: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
})
defineEmits(['finish'])

// The storefront is served from the same site as the dashboard.
const storeUrl = window.location.origin
const storeHost = window.location.host

async function copyLink() {
  try {
    await navigator.clipboard.writeText(storeUrl)
    toast.success('Copied')
  } catch {
    toast.error('Could not copy the link')
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center gap-2 rounded-4 bg-surface-gray-2 py-1 pl-3 pr-1">
      <span class="min-w-0 flex-1 truncate text-base text-ink-gray-8" data-onboarding-store-url>{{ storeHost }}</span>
      <Button variant="ghost" icon="lucide-copy" aria-label="Copy store link" @click="copyLink" />
      <Button variant="ghost" icon="lucide-external-link" aria-label="Open store" :href="storeUrl" />
    </div>
    <Button
      variant="solid"
      size="md"
      class="w-full"
      label="Go to dashboard"
      :loading="finishing || !isReady"
      @click="$emit('finish')"
    />
  </div>
</template>
