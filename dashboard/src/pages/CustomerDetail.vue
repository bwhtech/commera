<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Avatar, Badge, Button, Dropdown, FormControl, Skeleton, dayjs, toast } from 'frappe-ui'
import { BarChart } from 'frappe-ui/charts'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ReportStats from '../components/ReportStats.vue'
import StatusBadge from '../components/StatusBadge.vue'
import Thumb from '../components/Thumb.vue'
import EmptyState from '../components/EmptyState.vue'
import ExtensionActionDialog from '../components/ExtensionActionDialog.vue'
import ExtensionSlot from '../components/ExtensionSlot.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { erpnextLink } from '../data/erpnext'
import { errorMessage } from '../data/errors'
import { longDate, money } from '../data/format'
import { orderRoute, productRoute } from '../ia/routes'
import { useRecordExtensions } from '../data/recordExtensions'

const LAPSED_AFTER_DAYS = 90

const route = useRoute()

const customerRequest = useAdminRead('customers.get_customer', {
  params: () => ({ customer: route.params.id }),
  refetch: true,
})

const customer = computed(() => customerRequest.data)
const theirOrders = computed(() => customer.value?.recent_orders ?? [])
const topProducts = computed(() => customer.value?.top_products ?? [])

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

const daysSinceLastOrder = computed(() =>
  customer.value?.last_order ? dayjs().diff(dayjs(customer.value.last_order), 'day') : null,
)

const lifecycle = computed(() => {
  if (!customer.value?.orders) return { label: 'No orders yet', theme: 'gray' }
  if (daysSinceLastOrder.value > LAPSED_AFTER_DAYS) return { label: 'Lapsed', theme: 'red' }
  if (customer.value.orders > 1) return { label: 'Repeat', theme: 'green' }
  return { label: 'New', theme: 'blue' }
})

const stats = computed(() => [
  { label: 'Orders', value: customer.value.orders },
  { label: 'Lifetime spend', value: money(customer.value.spend) },
  {
    label: 'Avg spend per order',
    value: customer.value.orders ? money(customer.value.average_order) : '—',
  },
  {
    label: 'Last order',
    value: customer.value.last_order ? dayjs(customer.value.last_order).fromNow() : '—',
  },
])

const atAGlance = computed(() => {
  const record = customer.value
  const facts = []

  if (record.first_order) facts.push({ label: 'First order', value: longDate(record.first_order) })
  if (record.days_between_orders) {
    facts.push({ label: 'Orders about every', value: `${record.days_between_orders} days` })
  }
  if (record.units) facts.push({ label: 'Units bought', value: record.units })
  if (record.payment_mode) facts.push({ label: 'Usually pays by', value: record.payment_mode })
  if (record.acquisition?.source) {
    facts.push({
      label: 'Came from',
      value: [record.acquisition.source, record.acquisition.campaign].filter(Boolean).join(' · '),
      capitalize: true,
    })
  }
  return facts
})

const customerFor = computed(() => dayjs(customer.value.since).fromNow(true))

const spendByMonth = computed(() => {
  const months = customer.value?.spend_by_month ?? []
  const firstMonthWithSpend = months.findIndex((month) => month.spend)
  return firstMonthWithSpend > 0 ? months.slice(firstMonthWithSpend) : months
})

const contactLine = computed(() =>
  [customer.value.email, customer.value.phone, customer.value.city].filter(Boolean).join(' · '),
)

const note = ref('')
watch(customer, (record) => (note.value = record?.note ?? ''), { immediate: true })

const noteAction = useAdminAction('customers.save_customer_note')
const noteChanged = computed(() => note.value !== (customer.value?.note ?? ''))

async function saveNote() {
  await noteAction.submit({ customer: route.params.id, note: note.value })
  if (noteAction.error) return
  toast.success('Note saved')
  customerRequest.reload()
}

const { cards, actionGroup, openAction, record, reload: reloadExtensions } = useRecordExtensions(
  'customer',
  'Customer',
  () => route.params.id,
  { onReload: () => customerRequest.reload() },
)

function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}
</script>

<template>
  <template v-if="customer">
    <AppPageHeader
      :title="customer.name"
      back-to="/customers"
      :breadcrumbs="[{ label: 'Customers', route: '/customers' }, { label: customer.name }]"
    >
      <template #actions>
        <!-- A customer has no actions of its own, so the menu only exists once an installed app adds one. -->
        <Dropdown v-if="actionGroup" :options="[actionGroup]">
          <Button icon="lucide-ellipsis" label="More actions" />
        </Dropdown>
        <Button label="View in ERP" icon-right="lucide-external-link" :link="erpnextLink('Customer', customer.id)" />
      </template>
    </AppPageHeader>

    <PageBody width="wide">
      <div class="flex items-start gap-3">
        <Avatar :label="customer.name" size="2xl" />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <p class="text-xl text-ink-gray-9">{{ customer.name }}</p>
            <Badge :label="lifecycle.label" :theme="lifecycle.theme" variant="subtle" />
          </div>
          <p class="mt-1 text-sm text-ink-gray-5">
            {{ contactLine || 'No contact details on file' }}
          </p>
          <p class="mt-1 text-sm text-ink-gray-5">
            Customer for {{ customerFor }} · since {{ longDate(customer.since) }}
          </p>
        </div>
      </div>

      <ReportStats class="mt-6" :stats="stats" />

      <section v-if="atAGlance.length" class="mt-6 rounded-5 border border-outline-gray-1 px-4 py-3.5">
        <dl class="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
          <div v-for="fact in atAGlance" :key="fact.label">
            <dt class="text-sm text-ink-gray-5">{{ fact.label }}</dt>
            <dd
              class="mt-0.5 text-base text-ink-gray-8 tabular-nums"
              :class="fact.capitalize ? 'capitalize' : ''"
            >
              {{ fact.value }}
            </dd>
          </div>
        </dl>
      </section>

      <section v-if="customer.orders" class="mt-8">
        <div class="flex items-baseline justify-between">
          <h2 class="text-lg-semibold text-ink-gray-8">Spend by month</h2>
          <span class="text-sm text-ink-gray-5">
            {{ spendByMonth.length === 1 ? 'This month' : `Last ${spendByMonth.length} months` }}
          </span>
        </div>
        <div class="mt-2 rounded-5 border border-outline-gray-1 p-4">
          <div class="h-56">
            <BarChart :data="spendByMonth" x="label" :y="['spend']" />
          </div>
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-baseline justify-between">
          <h2 class="text-lg-semibold text-ink-gray-8">Recent orders</h2>
          <span class="text-sm text-ink-gray-5">{{ plural(customer.orders, 'order') }} all time</span>
        </div>
        <ul
          v-if="theirOrders.length"
          class="mt-2 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-1"
        >
          <li v-for="order in theirOrders" :key="order.name">
            <router-link
              :to="orderRoute(order.name)"
              class="flex items-center gap-4 px-4 py-2.5 hover:bg-surface-gray-2"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-base text-ink-gray-8">{{ order.name }}</p>
                <p class="mt-0.5 text-sm text-ink-gray-5">
                  {{ longDate(order.placed_on) }} · {{ plural(order.item_count, 'item') }}
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <StatusBadge :status="order.payment_state.key" :label="order.payment_state.label" />
                <StatusBadge :status="order.state.key" :label="order.state.label" />
              </div>
              <p class="w-28 shrink-0 text-right text-base text-ink-gray-8 tabular-nums">
                {{ money(order.total) }}
              </p>
              <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4" aria-hidden="true" />
            </router-link>
          </li>
        </ul>
        <EmptyState v-else icon="lucide-shopping-bag" title="No orders yet" compact />
      </section>

      <div class="mt-8 grid items-start gap-8 lg:grid-cols-3">
        <section v-if="topProducts.length" class="lg:col-span-2">
          <div class="flex items-baseline justify-between">
            <h2 class="text-lg-semibold text-ink-gray-8">Recently bought</h2>
            <span class="text-sm text-ink-gray-5">{{ plural(customer.units, 'unit') }} all time</span>
          </div>
          <ul class="mt-2 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-1">
            <li v-for="product in topProducts" :key="product.item_code">
              <router-link
                :to="productRoute(product.product)"
                class="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-gray-2"
              >
                <Thumb :image="product.image" size="size-9" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-base text-ink-gray-8">{{ product.name }}</p>
                  <p class="mt-0.5 text-sm text-ink-gray-5">{{ product.item_code }}</p>
                </div>
                <div class="text-right">
                  <p class="text-base text-ink-gray-8 tabular-nums">{{ plural(product.units, 'unit') }}</p>
                  <p class="mt-0.5 text-sm text-ink-gray-5 tabular-nums">{{ money(product.spend) }}</p>
                </div>
                <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4" aria-hidden="true" />
              </router-link>
            </li>
          </ul>
        </section>

        <div class="space-y-6">
          <section class="rounded-5 border border-outline-gray-1 px-4 py-3.5">
            <h2 class="text-sm text-ink-gray-5">Default address</h2>
            <p v-if="customer.address" class="mt-1.5 whitespace-pre-line text-p-base text-ink-gray-7">
              {{ customer.address }}
            </p>
            <p v-else class="mt-1.5 text-p-base text-ink-gray-4">No address on file.</p>
          </section>

          <section>
            <label class="text-sm text-ink-gray-5" for="customer-note">Note</label>
            <FormControl
              id="customer-note"
              class="mt-1.5"
              type="textarea"
              :rows="3"
              v-model="note"
              placeholder="Anything worth remembering about this customer"
            />
            <Button
              v-if="noteChanged"
              class="mt-2"
              label="Save note"
              :loading="noteAction.loading"
              @click="saveNote"
            />
          </section>

          <ExtensionSlot :entries="cards" :record="record" frame="stack" @reload="reloadExtensions" />
        </div>
      </div>
    </PageBody>

    <ExtensionActionDialog v-model:entry="openAction" :record="record" @reload="reloadExtensions" />
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
      <div class="flex items-start gap-3">
        <Skeleton class="size-10 rounded-4" />
        <div class="space-y-2">
          <Skeleton class="h-6 w-48 rounded-4" />
          <Skeleton class="h-3.5 w-72 rounded-4" />
          <Skeleton class="h-3.5 w-56 rounded-4" />
        </div>
      </div>

      <section
        class="mt-6 grid grid-cols-2 rounded-5 border border-outline-gray-1 sm:grid-cols-4 sm:divide-x sm:divide-outline-gray-2"
      >
        <div v-for="placeholder in 4" :key="placeholder" class="px-4 py-3.5">
          <Skeleton class="h-3.5 w-20 rounded-4" />
          <Skeleton class="mt-1 h-7 w-24 rounded-4" />
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-baseline justify-between">
          <Skeleton class="h-5 w-32 rounded-4" />
          <Skeleton class="h-3.5 w-28 rounded-4" />
        </div>
        <div class="mt-1 divide-y divide-outline-gray-1">
          <div v-for="placeholder in 3" :key="placeholder" class="flex items-center gap-4 py-3.5">
            <div class="min-w-0 flex-1 space-y-2">
              <Skeleton class="h-4 w-44 rounded-4" />
              <Skeleton class="h-3.5 w-24 rounded-4" />
            </div>
            <Skeleton class="h-5 w-40 rounded-4" />
            <Skeleton class="h-5 w-20 rounded-4" />
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
