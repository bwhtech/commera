<script setup>
import { Button, SettingsBody, dayjs } from 'frappe-ui'
import SettingsPanelHeader from '../SettingsPanelHeader.vue'
import SettingsSkeleton from '../SettingsSkeleton.vue'
import EmptyState from '../../EmptyState.vue'
import WebhookHealthBadge from './WebhookHealthBadge.vue'
import { __ } from '../../../data/translation'
import { hostOf, pathOf, webhookStore } from '../../../data/webhooks'

const emit = defineEmits(['open', 'add'])

const { listRequest, webhooks } = webhookStore

function lastSent(webhook) {
  return webhook.last_sent_at ? __('Last sent {0}', [dayjs(webhook.last_sent_at).fromNow()]) : __('Nothing sent yet')
}

function eventCount(webhook) {
  const count = webhook.events.length
  return count === 1 ? __('1 event') : __('{0} events', [count])
}
</script>

<template>
  <SettingsPanelHeader
    :title="__('Webhooks')"
    :description="__('Send store events to another app, such as a headless storefront that refreshes its pages when a product changes.')"
  >
    <template v-if="webhooks.length" #actions>
      <Button variant="solid" theme="gray" icon-left="lucide-plus" :label="__('Add webhook')" @click="emit('add')" />
    </template>
  </SettingsPanelHeader>

  <SettingsBody v-scroll-fade>
    <!-- The refusal itself is already toasted by useAdminRead. This says why the panel is empty. -->
    <EmptyState
      v-if="listRequest.error && !listRequest.data"
      compact
      icon="lucide-lock"
      :title="__('Hidden from your role')"
      :description="__('Webhooks are only listed for a role that can read them.')"
    />

    <SettingsSkeleton v-else-if="!listRequest.data" class="mt-2" :rows="3" />

    <template v-else-if="webhooks.length">
      <ul class="mt-2 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
        <li v-for="webhook in webhooks" :key="webhook.name">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-4 px-2 py-3 text-start hover:bg-surface-gray-1"
            @click="emit('open', webhook.name)"
          >
            <span class="grid size-8 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-6">
              <span class="lucide-webhook size-4" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-base font-semibold text-ink-gray-8" :title="webhook.url">
                {{ hostOf(webhook.url) }}
              </span>
              <span class="mt-0.5 block truncate font-mono text-xs text-ink-gray-5">{{ pathOf(webhook.url) }}</span>
            </span>
            <span class="hidden w-36 shrink-0 text-end sm:block">
              <span class="block text-sm text-ink-gray-7">{{ eventCount(webhook) }}</span>
              <span class="block text-xs text-ink-gray-5">{{ lastSent(webhook) }}</span>
            </span>
            <span class="flex shrink-0 justify-end sm:w-32">
              <WebhookHealthBadge :webhook="webhook" />
            </span>
            <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4 rtl:-scale-x-100" aria-hidden="true" />
          </button>
        </li>
      </ul>
      <p class="mt-4 text-p-sm text-ink-gray-5">
        {{ __("Each request is signed with the webhook's secret. Failed deliveries retry after 1, 5, 30, 120 and 360 minutes. After 10 failed attempts within 24 hours, Commera turns the webhook off.") }}
      </p>
    </template>

    <EmptyState
      v-else
      icon="lucide-webhook"
      :title="__('No webhooks yet')"
      :description="__('Add one to tell a headless storefront or another app when products, stock or orders change.')"
    >
      <Button class="mt-2" variant="solid" theme="gray" icon-left="lucide-plus" :label="__('Add webhook')" @click="emit('add')" />
    </EmptyState>
  </SettingsBody>
</template>
