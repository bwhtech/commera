<script setup>
/**
 * Who the order is for. It rides the right rail on desktop and stacks under
 * the items on a phone, so the same four sections have to render twice.
 */
import { Avatar, Badge } from 'frappe-ui'
import { customerRoute } from '../ia/routes'

defineProps({
  order: { type: Object, required: true },
})
</script>

<template>
  <div class="divide-y divide-outline-gray-1">
    <section class="px-4 py-4">
      <p class="text-sm text-ink-gray-5">{{ __('Customer') }}</p>
      <router-link :to="customerRoute(order.customer_id)" class="mt-2 flex items-center gap-2.5">
        <Avatar :label="order.customer" size="md" />
        <div class="min-w-0">
          <p class="truncate text-base text-ink-gray-8">{{ order.customer }}</p>
          <p v-if="order.phone" class="truncate text-sm text-ink-gray-5">{{ order.phone }}</p>
        </div>
      </router-link>
      <p v-if="order.email" class="mt-3 truncate text-sm text-ink-blue-link">{{ order.email }}</p>
    </section>

    <section class="px-4 py-4">
      <p class="text-sm text-ink-gray-5">{{ __('Shipping address') }}</p>
      <p class="mt-1.5 whitespace-pre-line text-p-base text-ink-gray-7">
        {{ order.shipping_address || __('No shipping address on file.') }}
      </p>
    </section>

    <section class="px-4 py-4">
      <p class="text-sm text-ink-gray-5">{{ __('Tags') }}</p>
      <div class="mt-1.5 flex flex-wrap gap-1.5">
        <Badge v-for="tag in order.tags" :key="tag" :label="tag" variant="subtle" />
        <span v-if="!order.tags.length" class="text-sm text-ink-gray-5">{{ __('None') }}</span>
      </div>
    </section>

    <section class="px-4 py-4">
      <p class="text-sm text-ink-gray-5">{{ __('Note') }}</p>
      <!-- Sales Order carries no note/remarks field in this data model — always the empty
           state rather than a control that can never do anything. -->
      <p class="mt-1.5 text-p-base text-ink-gray-4">{{ __('No note on this order.') }}</p>
    </section>
  </div>
</template>
