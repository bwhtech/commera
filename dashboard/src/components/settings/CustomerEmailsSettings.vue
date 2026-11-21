<script setup>
import { ref, watch } from 'vue'
import { Badge, Button, SettingsBody, Switch, Tooltip, toast } from 'frappe-ui'
import CustomerEmailDetail from './CustomerEmailDetail.vue'
import EmptyState from '../EmptyState.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminRead } from '../../data/api'
import { customerEmailActions } from '../../data/customerEmails'
import { __ } from '../../data/translation'
import { onSettingsClose } from '../../ia/settings'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const listRequest = useAdminRead('customer_emails.get_customer_emails', { immediate: false })
const emails = ref([])
const openEmail = ref(null)
const savingEmail = ref(null)

onSettingsClose(() => {
  openEmail.value = null
})

watch(
  () => props.active,
  (isActive) => {
    if (isActive && !listRequest.isFinished && !listRequest.loading) listRequest.reload()
  },
  { immediate: true },
)

watch(
  () => listRequest.data,
  (rows) => {
    if (rows) emails.value = rows
  },
  { immediate: true },
)

function applyRow(row) {
  emails.value = emails.value.map((email) => (email.email === row.email ? row : email))
}

async function setEnabled(email, enabled) {
  savingEmail.value = email.email
  const row = await customerEmailActions.call('set_email_enabled', { email: email.email, enabled })
  savingEmail.value = null
  if (!row) return
  applyRow(row)
  toast.success(enabled ? __('{0} is on', [row.label]) : __('{0} is off', [row.label]))
}
</script>

<template>
  <CustomerEmailDetail
    v-if="openEmail"
    :key="openEmail.email"
    :email="openEmail"
    @updated="(row) => { applyRow(row); openEmail = row }"
    @back="openEmail = null"
  />

  <template v-else>
    <SettingsPanelHeader
      :title="__('Emails')"
      :description="__('What your store emails shoppers. Open one to preview it, send yourself a test or pick its template.')"
    />

    <SettingsBody v-scroll-fade>
      <EmptyState
        v-if="listRequest.error && !listRequest.data"
        compact
        icon="lucide-triangle-alert"
        :title="__('These could not be loaded')"
        :description="__('Your emails still go out. This panel just cannot say which ones.')"
      >
        <Button :label="__('Try again')" variant="subtle" theme="gray" @click="listRequest.reload()" />
      </EmptyState>

      <SettingsSkeleton v-else-if="!listRequest.data" :rows="5" />

      <div v-else class="divide-y divide-outline-gray-1">
        <div v-for="email in emails" :key="email.email" class="flex items-center gap-3 py-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <p class="truncate text-base text-ink-gray-8">{{ email.label }}</p>
              <Badge v-if="email.always_on" :label="__('Always on')" theme="gray" variant="subtle" />
              <Badge v-if="email.email_template" :label="__('Custom template')" theme="gray" variant="subtle" />
            </div>
            <p v-if="email.description" class="mt-1 text-sm text-ink-gray-5">{{ email.description }}</p>
          </div>

          <div class="ms-auto flex shrink-0 items-center gap-2">
            <Button :label="__('Open')" @click="openEmail = email" />
            <Tooltip
              v-if="email.always_on"
              :text="__('Always on: shoppers need it to sign in or open their order.')"
            >
              <span class="flex">
                <Switch :model-value="true" size="sm" disabled :aria-label="__('{0} is always on', [email.label])" />
              </span>
            </Tooltip>
            <Switch
              v-else
              :model-value="email.enabled"
              size="sm"
              :disabled="savingEmail === email.email"
              :aria-label="__('Send {0}', [email.label])"
              @update:model-value="setEnabled(email, $event)"
            />
          </div>
        </div>
      </div>
    </SettingsBody>
  </template>
</template>
