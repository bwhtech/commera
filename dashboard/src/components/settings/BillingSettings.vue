<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ErrorMessage } from 'frappe-ui'
import { closeCloudSettings, openCloudSettings } from '@frappe/cloud-sdk'
import { cloudContext, refreshBilling } from '../../data/cloudBilling'

// True while one of the Cloud panel's own menus or dialogs is open; AppSettingsDialog's
// setOpen explains why Settings must not close then.
const overlayOpen = defineModel('overlayOpen', { type: Boolean, default: false })

const target = ref(null)
const error = ref('')
let overlayWatcher

// The runtime toggles `overlay-open` on its <fc-cloud-settings> host whenever a layer opens.
function watchOverlays() {
  const host = target.value?.querySelector('fc-cloud-settings')
  if (!host) return
  overlayWatcher = new MutationObserver(() => (overlayOpen.value = host.hasAttribute('overlay-open')))
  overlayWatcher.observe(host, { attributes: true, attributeFilter: ['overlay-open'] })
}

onMounted(async () => {
  try {
    await openCloudSettings({
      context: cloudContext,
      target: target.value,
      panels: ['billing'],
      theme: 'auto',
      // Choosing a plan ends the trial, so the sidebar card reads the billing again.
      onClose: refreshBilling,
    })
    watchOverlays()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Could not open Frappe Cloud billing.'
  }
})

onUnmounted(() => {
  overlayWatcher?.disconnect()
  overlayOpen.value = false
  closeCloudSettings()
})
</script>

<template>
  <ErrorMessage v-if="error" class="p-6" :message="error" />
  <!-- The runtime's host is `height: 100%` and scrolls inside itself, so this box must take the
       panel's full height rather than its content's. -->
  <div v-else ref="target" class="min-h-0 flex-1" />
</template>
