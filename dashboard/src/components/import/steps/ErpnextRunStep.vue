<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Badge, Button, Progress, Spinner } from 'frappe-ui'
import { closeImport, goToStep, imp } from '../../../data/importFlow'
import {
  publishAction,
  publishErpnextImport,
  resumeErpnextPolling,
  startErpnextImport,
} from '../../../data/erpnextImport'
import { runPercent } from '../../../data/erpnextImportState'
import { productRoute } from '../../../ia/routes'
import { productCount } from '../../../data/importCounts'
import NotPublishedList from '../NotPublishedList.vue'

startErpnextImport()

const status = computed(() => imp.erpnext.status)
const failures = computed(() => status.value?.failed ?? [])
const notPublished = computed(() => imp.erpnext.published?.not_published ?? [])
const created = computed(() => status.value?.created ?? 0)
const skipped = computed(() => status.value?.skipped ?? 0)

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
        <h2 class="text-xl-semibold text-ink-gray-9">{{ __('Importing your ERPNext items') }}</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">{{ __('You can close this window. The import keeps running.') }}</p>
      </div>

      <div class="rounded-5 border border-outline-gray-1 p-5">
        <div class="flex items-center gap-3">
          <Spinner class="size-4" />
          <span class="text-base text-ink-gray-8">
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
      <Alert v-else :description="__('Every item lands as a draft product. Nothing goes live until you publish.')" />
    </template>

    <template v-else-if="imp.phase === 'failed'">
      <div class="rounded-6 border border-outline-gray-1 px-6 py-8 text-center">
        <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-red-2 text-ink-red-6">
          <span class="lucide-triangle-alert size-6" aria-hidden="true" />
        </div>
        <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ __('The import could not finish') }}</h2>
        <p class="mx-auto mt-1.5 max-w-md text-p-base text-ink-gray-6">
          {{
            imp.erpnext.error ||
            __('It stopped before the end. The products it already made are kept, so running it again picks up the rest.')
          }}
        </p>
        <div class="mt-4 flex flex-wrap items-center justify-center gap-2">
          <Button variant="solid" theme="gray" icon-left="lucide-arrow-left rtl:-scale-x-100" :label="__('Back to items')" @click="backToPick" />
          <Button :label="__('Close')" @click="closeImport" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="rounded-6 border border-outline-gray-1 px-6 py-8 text-center">
        <template v-if="!imp.erpnext.published">
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-7">
            <span class="lucide-package-check size-6" aria-hidden="true" />
          </div>
          <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ created === 1 ? __('1 product added as a draft') : __('{0} products added as drafts', [created]) }}</h2>
          <p class="mx-auto mt-1.5 max-w-md text-p-base text-ink-gray-6">
            {{ __('Drafts are not on your store yet. Publish them now, or later from each product page.') }}
          </p>
          <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
            <Button
              variant="solid"
              theme="gray"
              :label="__('Publish all')"
              :loading="publishAction.loading"
              @click="publishErpnextImport"
            />
            <Button :label="__('View products')" @click="finish('/products')" />
          </div>
        </template>

        <template v-else>
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-green-2 text-ink-green-7">
            <span class="lucide-circle-check size-6" aria-hidden="true" />
          </div>
          <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ imp.erpnext.published.published === 1 ? __('1 product is live') : __('{0} products are live', [imp.erpnext.published.published]) }}</h2>
          <p class="mx-auto mt-1.5 max-w-md text-p-base text-ink-gray-6">
            {{
              notPublished.length
                ? __('{0} could not go live yet. Each one below says what it still needs.', [productCount(notPublished.length)])
                : __('Customers can find them on your store now.')
            }}
          </p>
          <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
            <Button variant="solid" theme="gray" :label="__('View products')" @click="finish('/products')" />
            <Button :label="__('Back to overview')" @click="finish('/')" />
          </div>
        </template>
      </div>

      <!-- One line per count on a phone: three stacked cards would push the lists below off screen. -->
      <div class="grid grid-cols-3 gap-2 sm:gap-4">
        <div class="rounded-5 border border-outline-gray-1 p-3 sm:p-4">
          <div class="text-2xl text-ink-gray-9 tabular-nums">{{ created }}</div>
          <div class="mt-0.5 text-sm text-ink-gray-5">{{ created === 1 ? __('product created') : __('products created') }}</div>
        </div>
        <div class="rounded-5 border border-outline-gray-1 p-3 sm:p-4">
          <div class="text-2xl text-ink-gray-9 tabular-nums">{{ skipped }}</div>
          <div class="mt-0.5 text-sm text-ink-gray-5">
            {{ skipped === 1 ? __('already a product, left alone') : __('already products, left alone') }}
          </div>
        </div>
        <div class="rounded-5 border border-outline-gray-1 p-3 sm:p-4">
          <div class="flex items-baseline gap-2">
            <span class="text-2xl tabular-nums" :class="failures.length ? 'text-ink-red-6' : 'text-ink-gray-9'">{{ failures.length }}</span>
            <Badge v-if="failures.length" class="hidden sm:inline-flex" :label="__('See below')" theme="red" variant="subtle" />
          </div>
          <div class="mt-0.5 text-sm text-ink-gray-5">
            {{ failures.length === 1 ? __('item that did not import') : __('items that did not import') }}
          </div>
        </div>
      </div>

      <NotPublishedList
        v-if="notPublished.length"
        :products="notPublished"
        @open="(itemTemplate) => finish(productRoute(itemTemplate))"
      />

      <div v-if="failures.length" class="rounded-5 border border-outline-gray-1">
        <div class="border-b border-outline-gray-1 px-4 py-3 text-base-semibold text-ink-gray-8">
          {{ __('Items that did not import') }}
        </div>
        <div v-scroll-fade class="max-h-56 divide-y divide-outline-gray-1 overflow-y-auto">
          <div v-for="failure in failures" :key="failure.item_code" class="flex items-start gap-3 px-4 py-2.5">
            <span class="shrink-0 text-sm text-ink-gray-5">{{ failure.item_code }}</span>
            <span class="text-sm text-ink-gray-7">{{ failure.error }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
