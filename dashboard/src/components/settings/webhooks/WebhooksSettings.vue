<script setup>
import { ref, watch } from 'vue'
import AddWebhookDialog from './AddWebhookDialog.vue'
import WebhookDetail from './WebhookDetail.vue'
import WebhookList from './WebhookList.vue'
import { webhookStore } from '../../../data/webhooks'

const props = defineProps({
  active: { type: Boolean, default: false },
})

// Local state, not a route: the panel lives inside the settings dialog, whose URL names only the tab.
const openName = ref(null)
const createdSecret = ref(null)
const isAddOpen = ref(false)

watch(
  () => props.active,
  (isActive) => isActive && webhookStore.loadOnce(),
  { immediate: true },
)

function openWebhook(name, secret = null) {
  createdSecret.value = secret
  openName.value = name
}

function onCreated({ name, secret }) {
  webhookStore.reload()
  openWebhook(name, secret)
}
</script>

<template>
  <WebhookDetail
    v-if="openName"
    :key="openName"
    :name="openName"
    :created-secret="createdSecret"
    @back="openWebhook(null)"
  />
  <WebhookList v-else @open="openWebhook" @add="isAddOpen = true" />

  <AddWebhookDialog v-model:open="isAddOpen" @created="onCreated" />
</template>
