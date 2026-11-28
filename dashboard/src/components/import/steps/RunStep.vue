<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Button, Spinner } from 'frappe-ui'
import {
  beginPhase,
  closeImport,
  endPhase,
  goToStep,
  imp,
  importParams,
  isCurrentImport,
  publishImportAction,
  publishImported,
} from '../../../data/importFlow'
import { useAdminAction, trySubmit } from '../../../data/api'
import { doneTitle, notPublishedBody, publishAllLabel, photoCount, publishedBody, resultRowName } from '../../../data/importCounts'
import { errorMessage } from '../../../data/errors'
import { __ } from '../../../data/translation'
import { productRoute } from '../../../ia/routes'
import ImportResult from '../ImportResult.vue'
import NotPublishedList from '../NotPublishedList.vue'
import ImportRowList from '../ImportRowList.vue'

// Quiet: a refused run ends on the failed card, which already says why. A toast repeated it.
const runImportAction = useAdminAction('imports.run_import', { quiet: true })

// run_import is one synchronous request that writes every product, so it has no progress to show
// and no way to cancel. Past this the merchant is told it is slow, not stuck, and that closing is safe.
const SLOW_RUN_MS = 45000
const slow = ref(false)
let slowTimer = null

async function run() {
  // beginPhase refuses while a run is in flight and once one has landed: a landed import must
  // never be written twice. A refused run (`failed`) is let through, for a retry from Review.
  const ticket = beginPhase('running')
  if (ticket === null) return
  slow.value = false
  slowTimer = setTimeout(() => (slow.value = true), SLOW_RUN_MS)

  const imported = await trySubmit(runImportAction, { ...importParams(), image_assignments: { ...imp.imageAssignments } })
  clearTimeout(slowTimer)
  slow.value = false
  if (!isCurrentImport(ticket)) return
  if (!imported) {
    endPhase(ticket, 'failed')
    return
  }
  const result = runImportAction.data
  imp.created = result.created
  imp.runRowErrors = result.row_errors
  imp.runRowWarnings = result.row_warnings ?? []
  imp.imagesAttached = result.images_attached
  imp.runImageErrors = result.image_errors
  endPhase(ticket, 'done')
}

onBeforeUnmount(() => clearTimeout(slowTimer))

// Started in setup rather than onMounted so the phase leaves `failed` before the first render: a
// retry mounts this component with the previous run's `failed` still set, and on mount the error
// branch would paint an empty card for a frame before the spinner replaced it.
run()

const router = useRouter()

function finish(path) {
  closeImport()
  router.push(path)
}

const published = computed(() => imp.published?.published ?? null)
const notPublished = computed(() => imp.published?.not_published ?? [])

// One entry per row, keyed by row and message: a product that failed to create reports every one of
// its rows, and a row can carry a photo error as well as a row error.
const rowEntries = (rows) =>
  rows.map((entry) => ({ key: `${entry.row}-${entry.message}`, name: resultRowName(entry), message: entry.message }))

const skippedTitle = computed(() =>
  imp.runRowErrors.length === 1 ? __('1 row was skipped') : __('{0} rows were skipped', [imp.runRowErrors.length]),
)
const warningsTitle = computed(() =>
  imp.runRowWarnings.length === 1
    ? __('1 row came in with a warning')
    : __('{0} rows came in with a warning', [imp.runRowWarnings.length]),
)

const doneBody = computed(() => {
  if (published.value != null) return publishedBody(published.value, notPublished.value.length)
  if (!imp.created.length) return __('Fix the rows below in your file, then import it again.')
  return notPublishedBody(imp.created.length)
})
</script>

<template>
  <div class="space-y-6">
    <template v-if="imp.phase === 'running'">
      <div>
        <h2 class="text-lg-semibold text-ink-gray-9">{{ __('Importing your products') }}</h2>
        <p class="mt-1.5 text-p-base text-ink-gray-6">{{ __('This only takes a moment.') }}</p>
      </div>

      <div class="flex items-center gap-3 rounded-5 border border-outline-gray-1 p-5">
        <Spinner class="size-4" />
        <span class="text-base text-ink-gray-8">
          {{ imp.counts.products === 1 ? __('Adding 1 product…') : __('Adding {0} products…', [imp.counts.products]) }}
        </span>
      </div>

      <Alert
        v-if="slow"
        theme="amber"
        :description="__('This is taking longer than usual. It is still running: you can close this window, and the products appear in your catalog when it finishes.')"
      />
    </template>

    <template v-else-if="imp.phase === 'failed'">
      <ImportResult failed :title="__('The import could not run')" :body="errorMessage(runImportAction.error)">
        <Button :label="__('Close')" @click="closeImport" />
        <Button variant="solid" theme="gray" icon-left="lucide-arrow-left rtl:-scale-x-100" :label="__('Back to review')" @click="goToStep('review')" />
      </ImportResult>
    </template>

    <template v-else>
      <ImportResult :published="published" :title="doneTitle(imp.created.length, published)" :body="doneBody">
        <template v-if="imp.imagesAttached" #details>
          <p class="mx-auto mt-1 max-w-md text-p-sm tabular-nums text-ink-gray-6">{{ __('{0} added.', [photoCount(imp.imagesAttached)]) }}</p>
        </template>
        <template v-if="published == null && imp.created.length">
          <Button :label="__('View products')" @click="finish('/products')" />
          <Button variant="solid" theme="gray" :label="publishAllLabel(imp.created.length)" :loading="publishImportAction.loading" @click="publishImported" />
        </template>
        <Button v-else variant="solid" theme="gray" :label="__('View products')" @click="finish('/products')" />
      </ImportResult>

      <NotPublishedList
        v-if="notPublished.length"
        :products="notPublished"
        @open="(itemTemplate) => finish(productRoute(itemTemplate))"
      />

      <ImportRowList v-if="imp.runRowErrors.length" :title="skippedTitle" :entries="rowEntries(imp.runRowErrors)" />

      <ImportRowList
        v-if="imp.runRowWarnings.length"
        tone="warning"
        :title="warningsTitle"
        :entries="rowEntries(imp.runRowWarnings)"
      />

      <!-- The server reports one entry per spreadsheet row of a group whose photos failed. -->
      <ImportRowList
        v-if="imp.runImageErrors.length"
        tone="warning"
        :title="__('Photos that did not attach')"
        :entries="rowEntries(imp.runImageErrors)"
        :footer="__('Add them from each product page.')"
      />
    </template>
  </div>
</template>
