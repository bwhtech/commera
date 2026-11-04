<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog, FormControl, TabButtons } from 'frappe-ui'
import WebhookEventPicker from './WebhookEventPicker.vue'
import { STOREFRONT_EVENTS, webhookActions } from '../../../data/webhooks'

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['created'])

const PRESETS = [
  { label: 'Headless storefront', value: 'storefront' },
  { label: 'Choose events', value: 'custom' },
]

const preset = ref('storefront')
const url = ref('')
const chosenEvents = ref([])
const saving = ref(false)

const urlError = computed(() =>
  url.value && !/^https?:\/\//.test(url.value) ? 'The URL must start with https:// or http://.' : '',
)
const events = computed(() => (preset.value === 'storefront' ? STOREFRONT_EVENTS : chosenEvents.value))
const canSave = computed(() => url.value && !urlError.value && events.value.length)

watch(open, (isOpen) => {
  if (!isOpen) return
  preset.value = 'storefront'
  url.value = ''
  chosenEvents.value = []
})

async function save() {
  saving.value = true
  const created = await webhookActions.call('create_webhook', { url: url.value.trim(), events: events.value })
  saving.value = false
  if (!created) return
  open.value = false
  emit('created', created)
}
</script>

<template>
  <Dialog v-model:open="open" title="Add webhook" size="2xl">
    <template #default>
      <div class="space-y-4">
        <FormControl
          v-model="url"
          type="url"
          label="Endpoint URL"
          description="Commera posts each event here as JSON."
          placeholder="https://shop.example.com/api/webhooks/commera"
          :error="urlError"
          required
        />
        <div>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span class="text-sm text-ink-gray-6">Events</span>
            <TabButtons v-model="preset" :options="PRESETS" aria-label="Events" />
          </div>
          <p v-if="preset === 'storefront'" class="mt-2 text-p-sm text-ink-gray-5">
            Sends product, stock, collection, page and menu changes, so your storefront refreshes the pages they touch.
          </p>
          <div v-else class="mt-3 max-h-80 overflow-y-auto pr-1">
            <WebhookEventPicker v-model="chosenEvents" />
          </div>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Cancel" @click="open = false" />
        <Button
          variant="solid"
          theme="gray"
          label="Add webhook"
          :disabled="!canSave"
          :loading="saving"
          @click="save"
        />
      </div>
    </template>
  </Dialog>
</template>
