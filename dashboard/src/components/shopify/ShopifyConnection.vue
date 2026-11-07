<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, FormControl, dialog, toast } from 'frappe-ui'
import { disconnect, saveConnection, shopify } from '../../data/shopifyImport'
import { longDate } from '../../data/format'

const AUTH_OPTIONS = [
  { label: 'Client ID and Secret (Dev Dashboard app)', value: 'Client Credentials' },
  { label: 'Admin API access token', value: 'Access Token' },
]

const connection = computed(() => shopify.overview?.connection ?? {})
const editing = ref(false)
const saving = ref(false)
const form = reactive({
  shop_domain: '',
  auth_method: 'Client Credentials',
  client_id: '',
  client_secret: '',
  access_token: '',
  api_version: '',
})

// The secrets never come back from the server, so the form starts them blank and a blank
// secret on save keeps the stored one (see shopify_import.save_connection).
watch(
  connection,
  (value) => {
    Object.assign(form, {
      shop_domain: value.shop_domain ?? '',
      auth_method: value.auth_method || 'Client Credentials',
      client_id: value.client_id ?? '',
      client_secret: '',
      access_token: '',
      api_version: value.api_version ?? '',
    })
    editing.value = !value.is_configured
  },
  { immediate: true },
)

const usesClientCredentials = computed(() => form.auth_method === 'Client Credentials')

async function connect() {
  saving.value = true
  const overview = await saveConnection({ ...form })
  saving.value = false
  if (overview) toast.success(`Connected to ${overview.connection.shop_name}`)
}

function confirmDisconnect() {
  dialog.confirm({
    title: 'Disconnect Shopify?',
    message: 'The stored credentials are removed. Everything already imported stays.',
    onConfirm: disconnect,
  })
}
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-5">
    <div class="flex items-start gap-3">
      <span class="lucide-shopping-bag mt-0.5 size-5 shrink-0 text-ink-gray-7" aria-hidden="true" />
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-lg-semibold text-ink-gray-9">Shopify store</h2>
          <Badge v-if="connection.is_configured" label="Connected" theme="green" variant="subtle" />
        </div>
        <p v-if="connection.is_configured && !editing" class="mt-1 text-p-sm text-ink-gray-6">
          {{ connection.shop_name || connection.shop_domain }} · {{ connection.shop_domain }}
          <template v-if="connection.shop_currency"> · {{ connection.shop_currency }}</template>
          <template v-if="connection.connected_on"> · checked {{ longDate(connection.connected_on) }}</template>
        </p>
        <p v-else class="mt-1 text-p-sm text-ink-gray-6">
          Install your Shopify app on the store, then enter its details. Nothing is imported until you start an import.
        </p>
      </div>
      <div v-if="connection.is_configured && !editing" class="flex shrink-0 gap-2">
        <Button label="Change" @click="editing = true" />
        <Button label="Disconnect" @click="confirmDisconnect" />
      </div>
    </div>

    <form v-if="editing" class="mt-5 grid gap-4 sm:grid-cols-2" @submit.prevent="connect">
      <FormControl
        v-model="form.shop_domain"
        label="Store domain"
        placeholder="my-store.myshopify.com"
        class="sm:col-span-2"
        required
      />
      <FormControl v-model="form.auth_method" type="select" label="Sign in with" :options="AUTH_OPTIONS" />
      <FormControl
        v-model="form.api_version"
        label="API version"
        placeholder="2026-10"
        description="Change it only if Shopify asks for another version."
      />
      <template v-if="usesClientCredentials">
        <FormControl v-model="form.client_id" label="Client ID" required />
        <FormControl
          v-model="form.client_secret"
          type="password"
          label="Client secret"
          :placeholder="connection.has_client_secret ? 'Saved. Leave blank to keep it' : ''"
          :required="!connection.has_client_secret"
        />
      </template>
      <FormControl
        v-else
        v-model="form.access_token"
        type="password"
        label="Access token"
        class="sm:col-span-2"
        :placeholder="connection.has_access_token ? 'Saved. Leave blank to keep it' : 'shpat_…'"
        :required="!connection.has_access_token"
      />
      <div class="flex items-center gap-2 sm:col-span-2">
        <Button type="submit" variant="solid" theme="gray" label="Connect" :loading="saving" />
        <Button v-if="connection.is_configured" label="Cancel" @click="editing = false" />
      </div>
    </form>
  </section>
</template>
