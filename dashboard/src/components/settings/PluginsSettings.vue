<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, Icon, SettingsBody, SettingsRow, Skeleton, Switch, TabButtons, toast } from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import ListPagination from '../ListPagination.vue'
import ResponsiveButton from '../ResponsiveButton.vue'
import StatusBadge from '../StatusBadge.vue'
import { useAdminAction, useAdminRead } from '../../data/api'
import { eventLabel, statusKey, timeLabel, useDeliveryRetry } from '../../data/pluginEvents'
import { appIcon, pluginSettingsTabs, placeLabel, settingsTabValue } from '../../ia/plugins'
import { settings } from '../../ia/settings'
import { orderRoute } from '../../ia/routes'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const DELIVERY_TABS = [
  { label: 'All', value: 'all' },
  { label: 'Failed', value: 'Failed' },
]

const pluginsRequest = useAdminRead('plugins.get_plugins', { immediate: false })
const plugins = computed(() => pluginsRequest.data ?? [])

watch(
  () => props.active,
  (isActive) => isActive && !pluginsRequest.isFinished && pluginsRequest.reload(),
  { immediate: true },
)

const configuring = ref(null)
const current = computed(() => plugins.value.find((app) => app.app === configuring.value) ?? null)
const settingsTab = computed(() =>
  pluginSettingsTabs().find((tab) => tab.value === settingsTabValue(configuring.value)),
)

const deliveryStatus = ref('all')
const page = ref(1)
const pageSize = ref(20)

const deliveriesRequest = useAdminRead('plugins.get_plugin_deliveries', {
  params: () => ({
    app: configuring.value,
    status: deliveryStatus.value === 'all' ? undefined : deliveryStatus.value,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  immediate: false,
})
const deliveries = computed(() => deliveriesRequest.data?.rows ?? [])

watch([configuring, deliveryStatus, pageSize], () => (page.value = 1))
watch([configuring, deliveryStatus, page, pageSize], () => configuring.value && deliveriesRequest.reload())

function openPlugin(app) {
  deliveryStatus.value = app.failed_deliveries ? 'Failed' : 'all'
  configuring.value = app.app
}

function pluginCount(app) {
  const count = app.entries.length
  return count === 1 ? '1 addition to the dashboard' : `${count} additions to the dashboard`
}

const { retrying: retryingDelivery, retry: retryDeliveries } = useDeliveryRetry(() => {
  deliveriesRequest.reload()
  pluginsRequest.reload()
})

function retry(row) {
  return retryDeliveries(row.delivery, row.app, [row.delivery])
}

const storefrontSave = useAdminAction('plugins.set_storefront_enabled')

// Saves on change like every settings switch; a refused save puts the switch back.
async function setStorefront(enabled) {
  const plugin = current.value
  plugin.storefront = enabled
  await storefrontSave.submit({ app: plugin.app, enabled })
  if (storefrontSave.error) {
    plugin.storefront = !enabled
    return
  }
  toast.success(enabled ? `${plugin.title} now runs on your storefront` : `${plugin.title} is off your storefront`)
}
</script>

<template>
  <template v-if="!current">
    <SettingsPanelHeader title="Plugins" description="Plugins installed alongside Commera, and what they add to it." />

    <SettingsBody v-scroll-fade>
      <!-- The refusal itself is already toasted by useAdminRead. This says why the panel is empty. -->
      <EmptyState
        v-if="pluginsRequest.error"
        compact
        icon="lucide-lock"
        title="Hidden from your role"
        description="Installed plugins are only listed for a System Manager."
      />

      <div v-else-if="!pluginsRequest.data" class="divide-y divide-outline-gray-1" aria-hidden="true">
        <div v-for="row in 3" :key="row" class="flex items-center gap-3 py-3">
          <Skeleton class="size-4 shrink-0 rounded-4" />
          <div class="min-w-0 flex-1">
            <Skeleton class="h-4 w-32 rounded-4" />
            <Skeleton class="mt-2 h-3.5 w-48 rounded-4" />
          </div>
          <Skeleton class="h-7 w-16 rounded-4" />
        </div>
      </div>

      <EmptyState
        v-else-if="!plugins.length"
        compact
        icon="lucide-blocks"
        title="No plugins installed"
        description="Plugins built for Commera show up here once they are installed on this site."
      />

      <div v-else class="divide-y divide-outline-gray-1">
        <div v-for="app in plugins" :key="app.app" class="flex items-center gap-3 py-3">
          <Icon :name="appIcon(app.app, app.icon_url)" class="size-4 shrink-0 text-ink-gray-6" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <p class="truncate text-base text-ink-gray-8">{{ app.title }}</p>
              <span v-if="app.version" class="shrink-0 text-sm text-ink-gray-5">{{ app.version }}</span>
            </div>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{ pluginCount(app) }}
              <template v-if="app.problems.length"> · {{ app.problems.length }} not loaded</template>
            </p>
          </div>
          <Badge
            v-if="app.failed_deliveries"
            class="shrink-0"
            theme="red"
            variant="subtle"
            :label="`${app.failed_deliveries} failed`"
          />
          <Button class="shrink-0" label="Open" @click="openPlugin(app)" />
        </div>
      </div>
    </SettingsBody>
  </template>

  <template v-else>
    <SettingsConfigHeader
      :title="current.title"
      :description="current.version ? `Version ${current.version}` : current.app"
      @back="configuring = null"
    >
      <template v-if="settingsTab" #actions>
        <ResponsiveButton label="Open settings" icon="lucide-settings" @click="settings.tab = settingsTab.value" />
      </template>
    </SettingsConfigHeader>

    <SettingsBody v-scroll-fade>
      <SettingsRow
        v-if="current.storefront !== null"
        class="mt-2 border-b border-outline-gray-1"
        title="Run on the storefront"
        description="This plugin adds scripts or blocks to your store pages, such as a popup or a banner. They load only while this is on."
      >
        <Switch
          size="sm"
          :model-value="current.storefront"
          :disabled="storefrontSave.loading"
          @update:model-value="setStorefront"
        />
      </SettingsRow>

      <section class="mt-2">
        <h3 class="text-base font-medium text-ink-gray-8">What it adds</h3>
        <ul
          v-if="current.entries.length || current.problems.length"
          class="mt-2 divide-y divide-outline-gray-1 border-y border-outline-gray-1"
        >
          <li v-for="entry in current.entries" :key="`${entry.place}/${entry.name}`" class="py-2.5">
            <div class="flex items-baseline justify-between gap-3">
              <p class="min-w-0 truncate text-base text-ink-gray-8">{{ entry.label }}</p>
              <p class="shrink-0 text-sm text-ink-gray-5">{{ placeLabel(entry.place) }}</p>
            </div>
            <p v-if="entry.error" class="mt-1 text-p-sm text-ink-red-6">{{ entry.error }}</p>
          </li>
          <li v-for="problem in current.problems" :key="problem" class="py-2.5 text-p-sm text-ink-red-6">
            {{ problem }}
          </li>
        </ul>
        <p v-else class="mt-1 text-p-sm text-ink-gray-5">Nothing on the dashboard. It may still listen to orders.</p>
      </section>

      <section class="mt-8">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-base font-medium text-ink-gray-8">Recent deliveries</h3>
          <TabButtons v-model="deliveryStatus" size="sm" :options="DELIVERY_TABS" />
        </div>
        <p class="mt-1 text-p-sm text-ink-gray-5">Each time an order changes, Commera tells the plugin. A failed send can be retried.</p>

        <div v-if="deliveriesRequest.loading && !deliveriesRequest.data" class="mt-3 space-y-3" aria-hidden="true">
          <Skeleton v-for="row in 3" :key="row" class="h-10 w-full rounded-4" />
        </div>

        <EmptyState
          v-else-if="!deliveries.length"
          compact
          :icon="deliveryStatus === 'Failed' ? 'lucide-circle-check' : 'lucide-send'"
          :title="deliveryStatus === 'Failed' ? 'Nothing failed' : 'No deliveries yet'"
          :description="deliveryStatus === 'Failed' ? 'Every order update reached this plugin.' : 'This plugin has not been sent an order update.'"
        />

        <template v-else>
          <ul class="mt-3 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
            <li v-for="row in deliveries" :key="row.delivery" class="flex items-center gap-3 py-2.5">
              <div class="min-w-0 flex-1">
                <p class="truncate text-base text-ink-gray-8">{{ eventLabel(row.event) }}</p>
                <p class="mt-0.5 flex min-w-0 gap-1 text-sm text-ink-gray-5">
                  <router-link
                    v-if="row.reference_doctype === 'Sales Order'"
                    :to="orderRoute(row.reference_name)"
                    class="min-w-0 truncate font-medium text-ink-gray-7 hover:underline"
                  >
                    {{ row.reference_name }}
                  </router-link>
                  <span v-else class="min-w-0 truncate">{{ row.reference_name }}</span>
                  <span class="shrink-0">· {{ timeLabel(row) }}</span>
                </p>
              </div>
              <StatusBadge class="shrink-0" :status="statusKey(row)" />
              <Button
                v-if="row.status === 'Failed' && row.can_retry"
                class="shrink-0"
                size="sm"
                label="Retry"
                icon-left="lucide-rotate-cw"
                :loading="retryingDelivery === row.delivery"
                :disabled="Boolean(retryingDelivery)"
                @click="retry(row)"
              />
            </li>
          </ul>
          <ListPagination v-model:page="page" v-model:page-size="pageSize" :total="deliveriesRequest.data.total" />
        </template>
      </section>
    </SettingsBody>
  </template>
</template>
