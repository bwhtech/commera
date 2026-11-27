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
import { doneTitle, photoCount, productCount } from '../../../data/importCounts'
import { __ } from '../../../data/translation'
import { productRoute } from '../../../ia/routes'
import NotPublishedList from '../NotPublishedList.vue'

const runImportAction = useAdminAction('imports.run_import')

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

const doneBody = computed(() => {
  if (published.value != null) {
    return notPublished.value.length
      ? __('{0} could not go live yet. Each one below says what it still needs.', [productCount(notPublished.value.length)])
      : __('Customers can find them on your store now.')
  }
  if (!imp.created.length) return __('Fix the rows below in your file, then import it again.')
  return __('Drafts are not on your store yet. Publish them now, or later from each product page.')
})
</script>

<template>
  <div class="space-y-6">
    <template v-if="imp.phase === 'running'">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">{{ __('Importing your products') }}</h2>
        <p class="mt-1.5 text-p-base text-ink-gray-6">{{ __('This only takes a moment.') }}</p>
      </div>

      <div class="flex items-center gap-3 rounded-5 border border-outline-gray-1 p-5">
        <Spinner class="size-4" />
        <span class="text-base text-ink-gray-8">
          {{ imp.counts.products === 1 ? __('Adding 1 product as a draft…') : __('Adding {0} products as drafts…', [imp.counts.products]) }}
        </span>
      </div>

      <Alert
        v-if="slow"
        theme="amber"
        :description="__('This is taking longer than usual. It is still running: you can close this window, and the products appear in your catalog when it finishes.')"
      />
    </template>

    <template v-else-if="imp.phase === 'failed'">
      <div class="rounded-6 border border-outline-gray-1 px-6 py-8 text-center">
        <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-red-2 text-ink-red-6">
          <span class="lucide-triangle-alert size-6" aria-hidden="true" />
        </div>
        <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ __('The import could not run') }}</h2>
        <p class="mx-auto mt-1.5 max-w-md text-p-base text-ink-gray-6">{{ runImportAction.error?.message }}</p>
        <div class="mt-5 flex flex-wrap items-center justify-center gap-2">
          <Button :label="__('Close')" @click="closeImport" />
          <Button variant="solid" theme="gray" icon-left="lucide-arrow-left rtl:-scale-x-100" :label="__('Back to review')" @click="goToStep('review')" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="rounded-6 border border-outline-gray-1 px-6 py-8 text-center">
        <div
          class="mx-auto flex size-12 items-center justify-center rounded-full"
          :class="published != null ? 'bg-surface-green-2 text-ink-green-7' : 'bg-surface-gray-2 text-ink-gray-7'"
        >
          <span :class="[published != null ? 'lucide-circle-check' : 'lucide-package-check', 'size-6']" aria-hidden="true" />
        </div>
        <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ doneTitle(imp.created.length, published) }}</h2>
        <p class="mx-auto mt-1.5 max-w-md text-p-base text-ink-gray-6">{{ doneBody }}</p>
        <p v-if="imp.imagesAttached" class="mx-auto mt-1 max-w-md text-p-sm text-ink-gray-5">
          {{ __('{0} added to them.', [photoCount(imp.imagesAttached)]) }}
        </p>

        <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
          <template v-if="published == null && imp.created.length">
            <Button :label="__('View products')" @click="finish('/products')" />
            <Button variant="solid" theme="gray" :label="__('Publish all')" :loading="publishImportAction.loading" @click="publishImported" />
          </template>
          <Button v-else variant="solid" theme="gray" :label="__('View products')" @click="finish('/products')" />
        </div>
      </div>

      <NotPublishedList
        v-if="notPublished.length"
        :products="notPublished"
        @open="(itemTemplate) => finish(productRoute(itemTemplate))"
      />

      <div v-if="imp.runRowErrors.length" class="rounded-5 border border-outline-gray-1">
        <div class="border-b border-outline-gray-1 px-4 py-3 text-base-semibold text-ink-gray-8">
          {{ imp.runRowErrors.length === 1 ? __('1 row was skipped') : __('{0} rows were skipped', [imp.runRowErrors.length]) }}
        </div>
        <div v-scroll-fade class="max-h-56 divide-y divide-outline-gray-1 overflow-y-auto">
          <div v-for="rowError in imp.runRowErrors" :key="rowError.row" class="flex items-start gap-3 px-4 py-2.5">
            <span class="shrink-0 text-sm tabular-nums text-ink-gray-5">{{ __('Row {0}', [rowError.row]) }}</span>
            <span class="text-p-sm text-ink-gray-7">{{ rowError.message }}</span>
          </div>
        </div>
      </div>

      <div v-if="imp.runImageErrors.length" class="rounded-5 border border-outline-gray-1">
        <!-- The server reports one entry per spreadsheet row of a group whose photos failed. -->
        <div class="border-b border-outline-gray-1 px-4 py-3 text-base-semibold text-ink-gray-8">
          {{ __('Photos that did not attach') }}
        </div>
        <div v-scroll-fade class="max-h-56 divide-y divide-outline-gray-1 overflow-y-auto">
          <div v-for="imageError in imp.runImageErrors" :key="imageError.row + imageError.message" class="flex items-start gap-3 px-4 py-2.5">
            <span v-if="imageError.row" class="shrink-0 text-sm tabular-nums text-ink-gray-5">{{ __('Row {0}', [imageError.row]) }}</span>
            <span class="text-p-sm text-ink-gray-7">{{ imageError.message }}</span>
          </div>
        </div>
        <p class="border-t border-outline-gray-1 px-4 py-2.5 text-p-sm text-ink-gray-5">{{ __('Add them from each product page.') }}</p>
      </div>
    </template>
  </div>
</template>
