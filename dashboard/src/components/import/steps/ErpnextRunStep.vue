<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Button, Progress, Spinner } from 'frappe-ui'
import { closeImport, goToStep, imp } from '../../../data/importFlow'
import {
  publishAction,
  publishErpnextImport,
  resumeErpnextPolling,
  startErpnextImport,
} from '../../../data/erpnextImport'
import { runPercent } from '../../../data/erpnextImportState'
import { productRoute } from '../../../ia/routes'
import { doneTitle, notPublishedBody, publishAllLabel, publishedBody } from '../../../data/importCounts'
import ImportResult from '../ImportResult.vue'
import NotPublishedList from '../NotPublishedList.vue'
import ImportRowList from '../ImportRowList.vue'
import { __ } from '../../../data/translation'

startErpnextImport()

const status = computed(() => imp.erpnext.status)
const failures = computed(() => status.value?.failed ?? [])
const notPublished = computed(() => imp.erpnext.published?.not_published ?? [])
const created = computed(() => status.value?.created ?? 0)
const skipped = computed(() => status.value?.skipped ?? 0)
const published = computed(() => imp.erpnext.published?.published ?? null)
const failureEntries = computed(() =>
  failures.value.map((failure) => ({
    key: failure.item_code,
    name: failure.item_name || failure.item_code,
    message: failure.error,
  })),
)

const doneBody = computed(() => {
  if (published.value != null) return publishedBody(published.value, notPublished.value.length)
  if (!created.value) return __('Fix the items below in ERPNext, then import them again.')
  return notPublishedBody(created.value)
})

const router = useRouter()

function backToPick() {
  goToStep('pick')
}

function finish(path) {
  closeImport()
  router.push(path)
}
</script>

<template>
  <div class="space-y-6">
    <template v-if="imp.phase === 'running'">
      <div>
        <h2 class="text-lg-semibold text-ink-gray-9">{{ __('Importing your ERPNext items') }}</h2>
        <p class="mt-1.5 text-pretty text-p-base text-ink-gray-6">{{ __('You can close this window. The import keeps running.') }}</p>
      </div>

      <div class="rounded-5 border border-outline-gray-1 p-5">
        <div class="flex items-center gap-3">
          <Spinner class="size-4" />
          <span class="text-base tabular-nums text-ink-gray-8">
            {{ status?.total ? __('{0} of {1} items done', [status.done, status.total]) : __('Starting the import…') }}
          </span>
        </div>
        <Progress :value="runPercent(status)" size="sm" class="mt-3" />
      </div>

      <Alert
        v-if="imp.erpnext.poll === 'stalled'"
        theme="amber"
        :description="__('This is taking longer than usual. It may still be running.')"
        :primary-action="{ label: __('Check again'), onClick: resumeErpnextPolling }"
      />
      <Alert v-else :description="__('Every item comes in as not published. Nothing goes live until you publish.')" />
    </template>

    <template v-else-if="imp.phase === 'failed'">
      <ImportResult
        :failed="!imp.erpnext.otherImportRunning"
        :waiting="imp.erpnext.otherImportRunning"
        :title="imp.erpnext.otherImportRunning ? __('These items were not imported') : __('The import could not finish')"
        :body="imp.erpnext.error || __('It stopped before the end. The products it already made are kept, so running it again picks up the rest.')"
      >
        <Button :label="__('Close')" @click="closeImport" />
        <Button variant="solid" theme="gray" icon-left="lucide-arrow-left rtl:-scale-x-100" :label="__('Back to items')" @click="backToPick" />
      </ImportResult>
    </template>

    <template v-else>
      <ImportResult :published="published" :title="doneTitle(created, published)" :body="doneBody">
        <template v-if="skipped" #details>
          <p class="mx-auto mt-1 max-w-md text-p-sm tabular-nums text-ink-gray-6">
            {{
              skipped === 1
                ? __('1 item is already a product, so it was left alone.')
                : __('{0} items are already products, so they were left alone.', [skipped])
            }}
          </p>
        </template>
        <template v-if="published == null && created">
          <Button :label="__('View products')" @click="finish('/products')" />
          <Button variant="solid" theme="gray" :label="publishAllLabel(created)" :loading="publishAction.loading" @click="publishErpnextImport" />
        </template>
        <Button v-else variant="solid" theme="gray" :label="__('View products')" @click="finish('/products')" />
      </ImportResult>

      <NotPublishedList
        v-if="notPublished.length"
        :products="notPublished"
        @open="(itemTemplate) => finish(productRoute(itemTemplate))"
      />

      <ImportRowList
        v-if="failures.length"
        :title="failures.length === 1 ? __('1 item did not import') : __('{0} items did not import', [failures.length])"
        :entries="failureEntries"
      />
    </template>
  </div>
</template>
