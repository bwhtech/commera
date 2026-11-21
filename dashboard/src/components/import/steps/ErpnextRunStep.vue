<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Badge, Button, Progress, Spinner } from 'frappe-ui'
import { canRouteAway, closeImport, importExits, imp } from '../../../data/importFlow'
import { stepIndex } from '../../../data/importSteps'
import {
  publishAction,
  publishErpnextImport,
  resumeErpnextPolling,
  startErpnextImport,
} from '../../../data/erpnextImport'
import { runPercent } from '../../../data/erpnextImportState'
import { productRoute } from '../../../ia/routes'

startErpnextImport()

const status = computed(() => imp.erpnext.status)
const failures = computed(() => status.value?.failed ?? [])
const needsPhoto = computed(() => imp.erpnext.published?.needs_photo ?? [])

const router = useRouter()

function backToPick() {
  imp.step = stepIndex('erpnext', 'pick')
}

function finish(path) {
  closeImport()
  if (path) router.push(path)
}
</script>

<template>
  <div class="space-y-6">
    <template v-if="imp.phase === 'running'">
      <div>
        <h2 class="text-xl text-ink-gray-9">{{ __('Importing your ERPNext items') }}</h2>
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
        <h2 class="mt-4 text-xl text-ink-gray-9">{{ __('The import could not finish') }}</h2>
        <p class="mx-auto mt-1.5 max-w-[460px] text-p-base text-ink-gray-6">
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
          <h2 class="mt-4 text-2xl text-ink-gray-9">{{ status?.created === 1 ? __('1 product is ready as a draft') : __('{0} products are ready as drafts', [status?.created ?? 0]) }}</h2>
          <p class="mx-auto mt-1.5 max-w-[460px] text-p-base text-ink-gray-6">
            {{ __('Publish them to put them on your storefront. Products without a photo stay as drafts until you add one.') }}
          </p>
          <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
            <Button
              variant="solid"
              theme="gray"
              icon-left="lucide-rocket"
              :label="__('Publish all')"
              :loading="publishAction.loading"
              @click="publishErpnextImport"
            />
            <Button :label="importExits[0].label" @click="finish(importExits[0].path)" />
          </div>
        </template>

        <template v-else>
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-green-2 text-ink-green-7">
            <span class="lucide-party-popper size-6" aria-hidden="true" />
          </div>
          <h2 class="mt-4 text-2xl text-ink-gray-9">{{ imp.erpnext.published.published === 1 ? __('1 product is live') : __('{0} products are live', [imp.erpnext.published.published]) }}</h2>
          <p class="mx-auto mt-1.5 max-w-[460px] text-p-base text-ink-gray-6">
            {{
              needsPhoto.length === 1
                ? __('1 product needs a photo before it can go live.')
                : needsPhoto.length
                  ? __('{0} need a photo before they can go live.', [needsPhoto.length])
                  : __('Every imported product is on your storefront.')
            }}
          </p>
          <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
            <Button
              v-for="(exit, index) in importExits"
              :key="exit.label"
              :variant="index ? 'subtle' : 'solid'"
              theme="gray"
              :label="exit.label"
              @click="finish(exit.path)"
            />
          </div>
        </template>
      </div>

      <div class="grid gap-4 sm:grid-cols-3">
        <div class="rounded-5 border border-outline-gray-1 p-4">
          <div class="text-2xl text-ink-gray-9 tabular-nums">{{ status?.created ?? 0 }}</div>
          <div class="mt-0.5 text-sm text-ink-gray-5">{{ __('products created') }}</div>
        </div>
        <div class="rounded-5 border border-outline-gray-1 p-4">
          <div class="text-2xl text-ink-gray-9 tabular-nums">{{ status?.skipped ?? 0 }}</div>
          <div class="mt-0.5 text-sm text-ink-gray-5">{{ __('already products, left alone') }}</div>
        </div>
        <div class="rounded-5 border border-outline-gray-1 p-4">
          <div class="flex items-baseline gap-2">
            <span class="text-2xl text-ink-red-6 tabular-nums">{{ failures.length }}</span>
            <Badge v-if="failures.length" :label="__('See below')" theme="red" variant="subtle" />
          </div>
          <div class="mt-0.5 text-sm text-ink-gray-5">{{ __('items that did not import') }}</div>
        </div>
      </div>

      <div v-if="needsPhoto.length" class="rounded-5 border border-outline-gray-1">
        <div class="border-b border-outline-gray-1 px-4 py-3 text-base-semibold text-ink-gray-8">
          {{ needsPhoto.length === 1 ? __('1 needs a photo') : __('{0} need a photo', [needsPhoto.length]) }}
        </div>
        <div v-scroll-fade class="max-h-56 divide-y divide-outline-gray-1 overflow-y-auto">
          <div v-for="product in needsPhoto" :key="product.item_code" class="flex items-center gap-3 px-4 py-2.5">
            <div class="min-w-0 flex-1">
              <div class="truncate text-base text-ink-gray-8">{{ product.item_name }}</div>
              <div class="truncate text-sm text-ink-gray-5">{{ product.item_code }}</div>
            </div>
            <Button
              v-if="canRouteAway"
              variant="subtle"
              icon-right="lucide-chevron-right rtl:-scale-x-100"
              :label="__('Add a photo')"
              @click="finish(productRoute(product.item_code))"
            />
          </div>
        </div>
      </div>

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
