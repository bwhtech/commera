<script setup>
import { ref } from 'vue'
import { Button, SettingsBody, Skeleton, toast } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import StackedSettingsRow from './StackedSettingsRow.vue'
import { useAdminRead } from '../../data/api'
import { customerEmailActions, EMAIL_TEMPLATE_FIELD, EMAIL_TEMPLATE_OPTIONS_PATH } from '../../data/customerEmails'
import { __ } from '../../data/translation'

const props = defineProps({
  email: { type: Object, required: true },
})

const emit = defineEmits(['back', 'updated'])

const previewRequest = useAdminRead('customer_emails.get_email_preview', {
  params: () => ({ email: props.email.email }),
})

const savingTemplate = ref(false)
const sendingTest = ref(false)

async function setTemplate(emailTemplate) {
  if ((emailTemplate || null) === (props.email.email_template || null)) return
  savingTemplate.value = true
  const row = await customerEmailActions.call('set_email_template', {
    email: props.email.email,
    email_template: emailTemplate || null,
  })
  savingTemplate.value = false
  if (!row) return
  emit('updated', row)
  previewRequest.reload()
  toast.success(row.email_template ? __('Template saved') : __('Back to the built-in design'))
}

async function sendTest() {
  if (sendingTest.value) return
  sendingTest.value = true
  const answer = await customerEmailActions.call('send_test_email', { email: props.email.email })
  sendingTest.value = false
  if (answer) toast.success(__('Test email sent to {0}', [answer.recipient]))
}
</script>

<template>
  <SettingsConfigHeader :title="email.label" :description="email.description" @back="emit('back')">
    <template #actions>
      <Button
        variant="solid"
        theme="gray"
        icon-left="lucide-send"
        :label="__('Send test email')"
        :loading="sendingTest"
        :disabled="previewRequest.data?.needs_order"
        @click="sendTest"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <div class="divide-y divide-outline-gray-1">
      <StackedSettingsRow
        :title="__('Template')"
        :description="__('Leave it on the built-in design, or pick an Email Template you made in Desk.')"
      >
        <div class="flex flex-wrap items-center gap-2">
          <SettingsLinkControl
            :field="EMAIL_TEMPLATE_FIELD"
            :model-value="email.email_template ?? ''"
            :options-path="EMAIL_TEMPLATE_OPTIONS_PATH"
            :placeholder="__('Built-in design')"
            :disabled="savingTemplate"
            @update:model-value="setTemplate"
          />
          <Button
            v-if="email.email_template"
            :label="__('Use built-in design')"
            :loading="savingTemplate"
            @click="setTemplate(null)"
          />
        </div>
      </StackedSettingsRow>

      <div class="py-3.5">
        <EmptyState
          v-if="previewRequest.data?.needs_order"
          compact
          icon="lucide-shopping-bag"
          :title="__('Place a test order first')"
          :description="__('This email shows an order. Place one on your store, then come back to preview it.')"
        />

        <EmptyState
          v-else-if="previewRequest.error && !previewRequest.data"
          compact
          icon="lucide-triangle-alert"
          :title="__('The preview could not be drawn')"
          :description="__('Check the template it uses, then try again.')"
        >
          <Button :label="__('Try again')" variant="subtle" theme="gray" @click="previewRequest.reload()" />
        </EmptyState>

        <template v-else>
          <p class="text-sm text-ink-gray-5">{{ __('Subject') }}</p>
          <Skeleton v-if="!previewRequest.data" class="mt-1 h-5 w-64 max-w-full rounded-4" />
          <p v-else class="mt-1 text-base font-semibold text-ink-gray-8">{{ previewRequest.data.subject }}</p>

          <div class="mt-3 overflow-hidden rounded-5 border border-outline-gray-2 bg-white">
            <Skeleton v-if="!previewRequest.data" class="h-[40rem] w-full rounded-0" />
            <iframe
              v-else
              class="block h-[40rem] w-full"
              sandbox=""
              :srcdoc="previewRequest.data.html"
              :title="__('Preview of {0}', [email.label])"
            />
          </div>
        </template>
      </div>
    </div>
  </SettingsBody>
</template>
