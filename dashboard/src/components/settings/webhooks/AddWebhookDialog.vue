<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog, FormControl } from 'frappe-ui'
import WebhookEventPicker from './WebhookEventPicker.vue'
import { webhookActions } from '../../../data/webhooks'

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['created'])

const url = ref('')
const events = ref([])
const saving = ref(false)

const canSave = computed(() => url.value.trim() && events.value.length)

watch(open, (isOpen) => {
  if (!isOpen) return
  url.value = ''
  events.value = []
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
  <Dialog v-model:open="open" :title="__('Add webhook')" size="2xl">
    <template #default>
      <div class="space-y-4">
        <FormControl
          v-model="url"
          type="url"
          :label="__('Endpoint URL')"
          :description="__('Commera posts each event here as JSON.')"
          placeholder="https://shop.example.com/api/webhooks/commera"
          required
        />
        <div>
          <span class="text-sm text-ink-gray-6">{{ __('Events') }}</span>
          <div class="mt-2 max-h-80 overflow-y-auto pe-1">
            <WebhookEventPicker v-model="events" />
          </div>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          variant="solid"
          theme="gray"
          :label="__('Add webhook')"
          :disabled="!canSave"
          :loading="saving"
          @click="save"
        />
      </div>
    </template>
  </Dialog>
</template>
