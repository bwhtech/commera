<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Avatar, Button, Skeleton } from 'frappe-ui'
import { List, ListCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAdminRead } from '../data/api'
import { erpnextLink } from '../data/erpnext'
import { errorMessage } from '../data/errors'
import { longDate, money, shortDate } from '../data/format'
import { ia } from '../ia/store'

const route = useRoute()

const customerRequest = useAdminRead('customers.get_customer', {
  params: () => ({ customer: route.params.id }),
  refetch: true,
})

const customer = computed(() => customerRequest.data)
const theirOrders = computed(() => customer.value?.recent_orders ?? [])

// A merged or deleted customer, a typo in the URL and a permission refusal all
// settle the same way — a finished request holding no customer — so the wording
// is chosen from whether the request also kept an error. §2: useAdminRead
// already toasted that error; it is read here to word the page, not to re-toast.
const loadFailure = computed(() =>
  customerRequest.error
    ? {
        icon: 'lucide-triangle-alert',
        title: 'Could not load this customer',
        description: errorMessage(customerRequest.error),
      }
    : {
        icon: 'lucide-search-x',
        title: 'Customer not found',
        description: `No customer matches ${route.params.id}. They may have been deleted or merged.`,
      },
)
</script>

<template>
  <template v-if="customer">
    <AppPageHeader
      :title="customer.name"
      back-to="/customers"
      :breadcrumbs="[{ label: 'Customers', route: '/customers' }, { label: customer.name }]"
    >
      <template #actions>
        <Button label="View in ERP" icon-right="lucide-external-link" :link="erpnextLink('Customer', customer.id)" />
      </template>
    </AppPageHeader>

    <PageBody width="wide">
      <div class="flex items-center gap-3">
        <Avatar :label="customer.name" size="2xl" />
        <div>
          <p class="text-xl text-ink-gray-9">{{ customer.name }}</p>
          <p class="mt-1 text-sm text-ink-gray-5">
            {{ customer.email ?? 'No email on file' }} · {{ customer.city ?? 'No city on file' }} · since
            {{ longDate(customer.since) }}
          </p>
          <p class="mt-1 text-sm text-ink-gray-4">
            Contact and billing details are kept on the customer record.
          </p>
        </div>
      </div>

      <section
        class="mt-6 grid grid-cols-2 rounded-5 border border-outline-gray-1 sm:grid-cols-3 sm:divide-x sm:divide-outline-gray-2"
      >
        <div class="px-4 py-3.5">
          <p class="text-sm text-ink-gray-5">Orders</p>
          <p class="mt-1 text-2xl text-ink-gray-9 tabular-nums">{{ customer.orders }}</p>
        </div>
        <div class="px-4 py-3.5">
          <p class="text-sm text-ink-gray-5">Lifetime spend</p>
          <p class="mt-1 text-2xl text-ink-gray-9 tabular-nums">{{ money(customer.spend) }}</p>
        </div>
        <div class="px-4 py-3.5">
          <p class="text-sm text-ink-gray-5">Average order</p>
          <p class="mt-1 text-2xl text-ink-gray-9 tabular-nums">
            {{ customer.orders ? money(customer.average_order) : '—' }}
          </p>
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-baseline justify-between">
          <h2 class="text-lg-semibold text-ink-gray-8">Recent orders</h2>
          <span class="text-sm text-ink-gray-5">{{ customer.orders }} orders all time</span>
        </div>
        <div class="mt-1 overflow-x-auto">
          <List class="min-w-[34rem]" :row-height="Math.max(ia.density, 48)">
            <ListRows :items="theirOrders" row-key="name" v-slot="{ item }">
              <ListRow :to="`/orders/${item.name}`" :value="item.name">
                <ListCell>
                  <span class="text-base text-ink-gray-4 tabular-nums">{{ item.name }}</span>
                </ListCell>
                <ListCell>
                  <div class="min-w-0">
                    <p class="truncate text-base text-ink-gray-8">
                      {{ item.item_count }} item{{ item.item_count > 1 ? 's' : '' }} · {{ money(item.total) }}
                    </p>
                    <p class="mt-1 text-sm text-ink-gray-5">{{ shortDate(item.placed_on) }}</p>
                  </div>
                </ListCell>
                <ListCell>
                  <div class="flex items-center gap-3">
                    <StatusBadge :status="item.payment_state.key" :label="item.payment_state.label" />
                    <StatusBadge :status="item.state.key" :label="item.state.label" />
                    <span class="lucide-chevron-right size-4 text-ink-gray-4" aria-hidden="true" />
                  </div>
                </ListCell>
              </ListRow>
            </ListRows>
          </List>
        </div>

        <EmptyState v-if="!theirOrders.length" icon="lucide-shopping-bag" title="No orders yet" compact />
      </section>
    </PageBody>
  </template>

  <!-- The customer id is already in the route, so the header is real from the
       first frame and only the record below waits on the request — the same
       decision the order, product and variant screens make. -->
  <template v-else-if="customerRequest.loading">
    <AppPageHeader
      :title="route.params.id"
      back-to="/customers"
      :breadcrumbs="[{ label: 'Customers', route: '/customers' }, { label: route.params.id }]"
    />

    <PageBody width="wide">
      <div class="flex items-center gap-3">
        <Skeleton class="size-10 rounded-4" />
        <div class="space-y-2">
          <Skeleton class="h-6 w-48 rounded" />
          <Skeleton class="h-3.5 w-72 rounded" />
          <Skeleton class="h-3.5 w-56 rounded" />
        </div>
      </div>

      <section
        class="mt-6 grid grid-cols-2 rounded-5 border border-outline-gray-1 sm:grid-cols-3 sm:divide-x sm:divide-outline-gray-2"
      >
        <div v-for="placeholder in 3" :key="placeholder" class="px-4 py-3.5">
          <Skeleton class="h-3.5 w-20 rounded" />
          <Skeleton class="mt-1 h-7 w-24 rounded" />
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-baseline justify-between">
          <Skeleton class="h-5 w-32 rounded" />
          <Skeleton class="h-3.5 w-28 rounded" />
        </div>
        <div class="mt-1 divide-y divide-outline-gray-1">
          <div v-for="placeholder in 3" :key="placeholder" class="flex items-center gap-4 py-3.5">
            <Skeleton class="h-4 w-28 rounded" />
            <div class="min-w-0 flex-1 space-y-2">
              <Skeleton class="h-4 w-44 rounded" />
              <Skeleton class="h-3.5 w-24 rounded" />
            </div>
            <Skeleton class="h-5 w-20 rounded" />
          </div>
        </div>
      </section>
    </PageBody>
  </template>

  <!-- The request has settled with nothing to show. Without this branch a bad id
       or a refusal falls through every branch above and paints an empty screen. -->
  <template v-else>
    <AppPageHeader
      :title="route.params.id"
      back-to="/customers"
      :breadcrumbs="[{ label: 'Customers', route: '/customers' }, { label: route.params.id }]"
    />

    <PageBody width="wide">
      <EmptyState
        :icon="loadFailure.icon"
        :title="loadFailure.title"
        :description="loadFailure.description"
      >
        <Button label="Back to customers" variant="subtle" theme="gray" route="/customers" />
      </EmptyState>
    </PageBody>
  </template>
</template>

