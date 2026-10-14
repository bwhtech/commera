<script setup>
import { reactive, ref } from 'vue'
import { Badge, Button, SettingsBody, SettingsRow, Switch, toast } from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import SettingsFieldRows from './SettingsFieldRows.vue'

const props = defineProps({
  card: { type: Object, required: true },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['back', 'save'])

// A Password never arrives with its value — the server sends `is_set` and a null instead —
// so a secret starts blank and staying blank keeps whatever is stored.
const values = reactive(
  Object.fromEntries(
    props.card.groups.flatMap((group) =>
      group.fields.map((field) => [field.fieldname, field.is_secret ? '' : (field.value ?? '')]),
    ),
  ),
)

const enabled = ref(props.card.enabled)

// The clipboard is refused outright over plain http and in some embedded browsers,
// so the URL is put in front of the merchant to copy by hand.
async function copyWebhookUrl() {
  try {
    await navigator.clipboard.writeText(props.card.webhook_url)
    toast.success('Webhook URL copied')
  } catch {
    toast.error('Could not copy the webhook URL', { description: props.card.webhook_url })
  }
}
</script>

<template>
  <SettingsConfigHeader :title="card.label" :description="card.blurb" @back="emit('back')">
    <template #actions>
      <Button
        label="Save"
        variant="solid"
        theme="gray"
        :loading="saving"
        @click="emit('save', { enabled, values })"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <div class="divide-y divide-outline-gray-1">
      <SettingsRow title="Enabled" description="Offered to customers at checkout.">
        <div class="flex items-center gap-2">
          <Badge
            v-if="card.missing?.length"
            :label="`${card.missing.length} still needed`"
            theme="orange"
            variant="subtle"
          />
          <Switch v-model="enabled" size="sm" />
        </div>
      </SettingsRow>

      <!-- A Link here is a pickup Address or a currency: pickable, because a name typed from
           memory that does not match reads to the carrier as no origin at all. -->
      <SettingsFieldRows
        :groups="card.groups"
        :values="values"
        link-options-path="integrations.get_link_options"
        @update="(fieldname, value) => (values[fieldname] = value)"
      />
    </div>

    <!-- The provider needs this URL in its own panel, and it is the one thing here that
         is read rather than written, so it gets a copy button and no input. -->
    <div v-if="card.webhook_url" class="mt-6 border-t border-outline-gray-1 pt-4">
      <p class="text-sm text-ink-gray-5">Webhook URL</p>
      <div class="mt-2 flex items-center gap-2">
        <code class="min-w-0 flex-1 truncate rounded bg-surface-gray-2 px-2 py-1 text-sm text-ink-gray-7">
          {{ card.webhook_url }}
        </code>
        <Button label="Copy" icon-left="lucide-copy" @click="copyWebhookUrl" />
      </div>
      <p class="mt-2 text-sm text-ink-gray-5">
        Paste this into the provider's dashboard so it can report status back to this store.
      </p>
    </div>

    <div v-if="card.docs_url" class="mt-4">
      <Button
        label="Provider documentation"
        icon-right="lucide-external-link"
        variant="ghost"
        :href="card.docs_url"
      />
    </div>
  </SettingsBody>
</template>

