<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Badge, Button, Checkbox, Skeleton, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ShopifyConnection from '../components/shopify/ShopifyConnection.vue'
import ShopifyOptions from '../components/shopify/ShopifyOptions.vue'
import ShopifyScanReport from '../components/shopify/ShopifyScanReport.vue'
import ShopifyRunProgress from '../components/shopify/ShopifyRunProgress.vue'
import {
  COUNT_FOR_RESOURCE,
  RESOURCE_HINTS,
  STATUS_THEMES,
  isActive,
  loadOverview,
  loadRun,
  shopify,
  startImport,
  startScan,
} from '../data/shopifyImport'
import { longDate } from '../data/format'

const POLL_MILLISECONDS = 2000

const overview = computed(() => shopify.overview)
const isConfigured = computed(() => Boolean(overview.value?.connection.is_configured))
const running = computed(() => isActive(shopify.run))
const selectedResources = ref([])
const onlyChanged = ref(false)
const starting = ref(false)

loadOverview().then((data) => {
  if (!data) return
  selectedResources.value = [...data.resources]
  if (data.runs.length) loadRun(data.runs[0].name)
})

// A run is a background job, so the screen asks for it again until it ends. Polling stops on
// its own once the run is finished, and with the screen.
let pollTimer = null
watch(running, (isRunning, wasRunning) => {
  clearInterval(pollTimer)
  if (isRunning) {
    pollTimer = setInterval(() => !document.hidden && loadRun(shopify.run.name), POLL_MILLISECONDS)
  } else if (wasRunning) {
    loadOverview()
    toast.success(`${shopify.run.run_type} finished: ${shopify.run.status}`)
  }
})
onBeforeUnmount(() => clearInterval(pollTimer))

function toggleResource(resource, checked) {
  selectedResources.value = checked
    ? overview.value.resources.filter((name) => name === resource || selectedResources.value.includes(name))
    : selectedResources.value.filter((name) => name !== resource)
}

function scanCount(resource) {
  const count = overview.value?.latest_scan?.counts?.[COUNT_FOR_RESOURCE[resource]]
  return count === undefined || count === null ? null : count
}

async function run(action) {
  starting.value = true
  await action()
  starting.value = false
}
</script>

<template>
  <AppPageHeader title="Import from Shopify" :back-to="{ name: 'Products' }" />

  <PageBody width="narrow">
    <div v-if="!overview" class="space-y-4">
      <Skeleton v-for="block in 3" :key="block" class="h-32 w-full rounded-5" />
    </div>

    <div v-else class="space-y-6">
      <ShopifyConnection />

      <template v-if="isConfigured">
        <ShopifyOptions />

        <section class="rounded-5 border border-outline-gray-1 p-5">
          <div class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <h2 class="text-lg-semibold text-ink-gray-9">Scan</h2>
              <p class="mt-1 text-p-sm text-ink-gray-6">
                Reads the store without changing anything here, and lists what will not fit.
              </p>
            </div>
            <Button
              label="Scan store"
              icon-left="lucide-scan-search"
              :loading="starting"
              :disabled="running"
              @click="run(startScan)"
            />
          </div>
          <ShopifyScanReport v-if="overview.latest_scan" class="mt-5" :report="overview.latest_scan" />
        </section>

        <section class="rounded-5 border border-outline-gray-1 p-5">
          <h2 class="text-lg-semibold text-ink-gray-9">Import</h2>
          <p class="mt-1 text-p-sm text-ink-gray-6">
            Runs in the background. You can leave this page. Running it again updates what was imported before.
          </p>

          <div class="mt-4 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
            <label v-for="resource in overview.resources" :key="resource" class="flex items-center gap-3 py-3">
              <Checkbox
                :model-value="selectedResources.includes(resource)"
                @update:model-value="toggleResource(resource, $event)"
              />
              <div class="min-w-0 flex-1">
                <div class="text-base text-ink-gray-8">
                  {{ resource }}
                  <span v-if="scanCount(resource) !== null" class="text-ink-gray-5 tabular-nums">
                    · {{ scanCount(resource).toLocaleString() }}
                  </span>
                </div>
                <div class="text-p-sm text-ink-gray-5">{{ RESOURCE_HINTS[resource] }}</div>
              </div>
            </label>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-3">
            <Checkbox
              v-model="onlyChanged"
              :disabled="!overview.last_import_started_on"
              :label="
                overview.last_import_started_on
                  ? `Only what changed since ${longDate(overview.last_import_started_on)}`
                  : 'Only what changed (after the first import)'
              "
            />
            <Button
              class="ml-auto"
              variant="solid"
              theme="gray"
              icon-left="lucide-download"
              label="Start import"
              :loading="starting"
              :disabled="running || !selectedResources.length"
              @click="run(() => startImport(selectedResources, onlyChanged))"
            />
          </div>
        </section>

        <section v-if="shopify.run" class="rounded-5 border border-outline-gray-1 p-5">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-lg-semibold text-ink-gray-9">
              {{ shopify.run.run_type === 'Scan' ? 'Latest scan' : 'Latest import' }}
            </h2>
            <Badge :label="shopify.run.status" :theme="STATUS_THEMES[shopify.run.status]" variant="subtle" />
            <span v-if="shopify.run.started_on" class="text-sm text-ink-gray-5">
              {{ longDate(shopify.run.started_on) }}
            </span>
          </div>
          <ShopifyRunProgress class="mt-4" :run="shopify.run" />
        </section>
      </template>
    </div>
  </PageBody>
</template>
