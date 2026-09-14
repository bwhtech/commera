<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { KeyboardShortcut, useKeyboardShortcut } from 'frappe-ui'
import {
  CommandPalette,
  CommandPaletteEmpty,
  CommandPaletteFooter,
  CommandPaletteGroup,
  CommandPaletteInput,
  CommandPaletteItem,
  CommandPaletteList,
} from 'frappe-ui/experimental'
import EmptyState from './EmptyState.vue'
import { useAdminRead } from '../data/api'
import { money, priceRange } from '../data/format'
import { openSettings } from '../ia/settings'
import { search } from '../ia/search'
import { openImport } from '../data/importFlow'
import { openAddProduct } from '../data/addProduct'

const LIMIT = 5

const router = useRouter()
const query = ref('')

useKeyboardShortcut({
  combo: 'Mod+K',
  description: 'Search',
  handler: () => (search.open = !search.open),
  allowInInput: true,
})

const needle = computed(() => query.value.trim())

// `immediate: false` keeps this idle on mount — the palette is always in the DOM behind ⌘K, so an
// eager fetch would hit the backend on every page load before anyone has typed anything.
// `refetch: true` re-runs the call whenever `needle` changes the request's params, which is the
// only trigger this needs — no debounce here, matching how every other search box in this app
// (Products.vue, Customers.vue) fires on each keystroke.
const productsRequest = useAdminRead('catalog.get_products', {
  params: () => ({ search: needle.value || undefined, page_length: LIMIT }),
  immediate: false,
  refetch: true,
})
const ordersRequest = useAdminRead('orders.get_orders', {
  params: () => ({ search: needle.value || undefined, page_length: LIMIT }),
  immediate: false,
  refetch: true,
})
const customersRequest = useAdminRead('customers.get_customers', {
  params: () => ({ search: needle.value || undefined, page_length: LIMIT }),
  immediate: false,
  refetch: true,
})
const collectionsRequest = useAdminRead('catalog.list_collections', {
  params: () => ({ search: needle.value || undefined, page_length: LIMIT }),
  immediate: false,
  refetch: true,
})

// Records only appear once there is something to match; with an empty query the
// palette is a short list of what you most likely came for.
const productHits = computed(() => (needle.value ? (productsRequest.data?.products ?? []) : []))
const orderHits = computed(() => (needle.value ? (ordersRequest.data?.orders ?? []) : []))
const customerHits = computed(() => (needle.value ? (customersRequest.data?.customers ?? []) : []))
const collectionHits = computed(() => (needle.value ? (collectionsRequest.data?.collections ?? []) : []))

// Four requests re-fire on every keystroke, and a hit list that is briefly empty
// mid-flight is not a miss — without this the palette would flash "nothing matches"
// between every letter typed.
const searching = computed(
  () =>
    productsRequest.loading ||
    ordersRequest.loading ||
    customersRequest.loading ||
    collectionsRequest.loading,
)

const noRecordHits = computed(
  () =>
    Boolean(needle.value) &&
    !searching.value &&
    !productHits.value.length &&
    !orderHits.value.length &&
    !customerHits.value.length &&
    !collectionHits.value.length,
)

// The miss reads the same wherever it lands — inside the list above a group of matching
// commands, or in the palette's own empty slot — so both sites bind this one set.
const noMatchState = computed(() => ({
  compact: true,
  icon: 'lucide-search',
  title: `Nothing matches “${needle.value}”`,
  description: 'Try a product name, an order number, or a customer.',
}))

// Everything reachable by keyboard, including the screens the sidebar does not
// list — stock, prices and product types are reached from the catalogue, but
// they are still real destinations.
const GO_TO = [
  { id: 'go-home', label: 'Overview', icon: 'lucide-layout-dashboard', keywords: ['home', 'dashboard'], run: () => router.push('/') },
  { id: 'go-orders', label: 'Orders', icon: 'lucide-shopping-bag', keywords: ['sales'], run: () => router.push('/orders') },
  { id: 'go-customers', label: 'Customers', icon: 'lucide-users', keywords: ['people', 'buyers'], run: () => router.push('/customers') },
  { id: 'go-products', label: 'Products', icon: 'lucide-package', keywords: ['catalogue', 'catalog'], run: () => router.push('/products') },
  { id: 'go-inventory', label: 'Inventory', icon: 'lucide-boxes', keywords: ['stock', 'warehouse'], run: () => router.push('/inventory') },
  { id: 'go-pricing', label: 'Bulk edit prices', icon: 'lucide-indian-rupee', keywords: ['price', 'margin', 'reprice'], run: () => router.push('/pricing') },
  { id: 'go-revenue', label: 'Revenue report', icon: 'lucide-banknote', keywords: ['analytics', 'sales', 'refunds'], run: () => router.push('/analytics/revenue') },
  { id: 'go-stock-report', label: 'Inventory report', icon: 'lucide-chart-line', keywords: ['analytics', 'dead stock', 'cover'], run: () => router.push('/analytics/inventory') },
  { id: 'go-storefront-report', label: 'Storefront report', icon: 'lucide-globe', keywords: ['analytics', 'sessions', 'funnel'], run: () => router.push('/analytics/storefront') },
  { id: 'go-theme', label: 'Storefront theme', icon: 'lucide-palette', keywords: ['design', 'brand'], run: () => router.push('/storefront/theme') },
]

const CREATE = [
  { id: 'new-product', label: 'New product', icon: 'lucide-plus', keywords: ['add', 'create'], run: openAddProduct },
  { id: 'import', label: 'Import products from CSV', icon: 'lucide-upload', keywords: ['csv', 'bulk', 'shopify', 'migrate'], run: openImport },
  { id: 'receive', label: 'Receive stock', icon: 'lucide-package-plus', keywords: ['inward', 'grn'], run: () => router.push('/inventory') },
]

const SETTINGS = [
  { id: 'settings', label: 'Open settings', icon: 'lucide-settings', keywords: ['preferences', 'config'], run: () => openSettings('general') },
  { id: 'appearance', label: 'Appearance', icon: 'lucide-sun-moon', keywords: ['theme', 'dark', 'light'], run: () => openSettings('appearance') },
  { id: 'payments', label: 'Payment providers', icon: 'lucide-credit-card', keywords: ['stripe', 'razorpay', 'gateway'], run: () => openSettings('payments') },
  { id: 'apps', label: 'Apps and channels', icon: 'lucide-plug', keywords: ['integrations', 'shiprocket'], run: () => openSettings('apps') },
]

const ALL = [
  { label: 'Go to', commands: GO_TO },
  { label: 'Create', commands: CREATE },
  { label: 'Settings', commands: SETTINGS },
]

// Before you type, the palette is a short menu — the five destinations worth a
// shortcut. Dumping every command into an empty query is what made it a wall.
const SUGGESTED = [
  { label: 'Jump to', commands: GO_TO.slice(0, 5) },
  { label: 'Create', commands: CREATE.slice(0, 2) },
]

// The palette's own filter is off so the record rows can be ranked by hand;
// the command rows therefore have to filter here.
const commandGroups = computed(() => {
  if (!needle.value) return SUGGESTED
  return ALL.map((group) => ({
    label: group.label,
    commands: group.commands.filter((command) =>
      [command.label, ...command.keywords].some((text) => text.toLowerCase().includes(needle.value)),
    ),
  })).filter((group) => group.commands.length)
})

// Every id here is a real record name straight off the admin API (catalog.get_products'
// item_template, orders.get_orders' Sales Order name, customers.get_customers' Customer name) —
// the same class of link the Dashboard's recent-orders/top-products rows needed fixing for, since
// this palette is reachable from every screen at all times.
function onSelect(value) {
  if (value.kind === 'product') return router.push(`/products/${value.id}`)
  if (value.kind === 'order') return router.push(`/orders/${value.id}`)
  if (value.kind === 'customer') return router.push(`/customers/${value.id}`)
  if (value.kind === 'collection') return router.push('/collections')
  ALL.flatMap((group) => group.commands).find((command) => command.id === value.id)?.run()
}
</script>

<template>
  <CommandPalette
    v-model:open="search.open"
    v-model:query="query"
    class="palette"
    :filterable="false"
    title="Search Commera"
    @select="onSelect"
  >
    <CommandPaletteInput placeholder="Search products, orders and customers, or type a command…" />

    <!-- One scroll region, capped: the list never grows past the fold. -->
    <CommandPaletteList class="max-h-[21rem] py-1.5">
      <CommandPaletteGroup v-if="productHits.length" label="Products">
        <CommandPaletteItem
          v-for="product in productHits"
          :key="product.name"
          :value="{ kind: 'product', id: product.name }"
        >
          <template #prefix>
            <span class="lucide-package mr-2.5 size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
          </template>
          {{ product.title }}
          <template #suffix>
            <span class="text-sm text-ink-gray-5">{{ priceRange(product.price_from, product.price_to) }}</span>
          </template>
        </CommandPaletteItem>
      </CommandPaletteGroup>

      <CommandPaletteGroup v-if="orderHits.length" label="Orders">
        <CommandPaletteItem
          v-for="order in orderHits"
          :key="order.name"
          :value="{ kind: 'order', id: order.name }"
        >
          <template #prefix>
            <span class="lucide-shopping-bag mr-2.5 size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
          </template>
          {{ order.name }} · {{ order.customer }}
          <template #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ money(order.total) }}</span>
          </template>
        </CommandPaletteItem>
      </CommandPaletteGroup>

      <CommandPaletteGroup v-if="customerHits.length" label="Customers">
        <CommandPaletteItem
          v-for="customer in customerHits"
          :key="customer.id"
          :value="{ kind: 'customer', id: customer.id }"
        >
          <template #prefix>
            <span class="lucide-user mr-2.5 size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
          </template>
          {{ customer.name }}
          <template #suffix>
            <span class="text-sm text-ink-gray-5">{{ customer.city }}</span>
          </template>
        </CommandPaletteItem>
      </CommandPaletteGroup>

      <CommandPaletteGroup v-if="collectionHits.length" label="Collections">
        <CommandPaletteItem
          v-for="collection in collectionHits"
          :key="collection.name"
          :value="{ kind: 'collection', id: collection.name }"
        >
          <template #prefix>
            <span class="lucide-layers mr-2.5 size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
          </template>
          {{ collection.name }}
          <template #suffix>
            <span class="text-sm text-ink-gray-5">{{ collection.count }} products</span>
          </template>
        </CommandPaletteItem>
      </CommandPaletteGroup>

      <!-- Commands that match the query still render below, and a group of them reads as
           a result list — so the miss has to be said out loud. When nothing matches at all
           the palette itself reports empty and the state moves to CommandPaletteEmpty
           below, which is why this one waits for a command group to sit under. -->
      <EmptyState v-if="noRecordHits && commandGroups.length" v-bind="noMatchState" />

      <CommandPaletteGroup v-for="group in commandGroups" :key="group.label" :label="group.label">
        <CommandPaletteItem
          v-for="command in group.commands"
          :key="command.id"
          :value="{ kind: 'command', id: command.id }"
        >
          <template #prefix>
            <span :class="[command.icon, 'mr-2.5 size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
          </template>
          {{ command.label }}
        </CommandPaletteItem>
      </CommandPaletteGroup>
    </CommandPaletteList>

    <CommandPaletteEmpty>
      <EmptyState v-bind="noMatchState" />
    </CommandPaletteEmpty>

    <CommandPaletteFooter>
      <span class="flex items-center gap-1.5 text-sm text-ink-gray-5">
        <KeyboardShortcut combo="ArrowUp" /><KeyboardShortcut combo="ArrowDown" /> Navigate
      </span>
      <span class="flex items-center gap-1.5 text-sm text-ink-gray-5">
        <KeyboardShortcut combo="Enter" /> Open
      </span>
      <span class="ml-auto flex items-center gap-1.5 text-sm text-ink-gray-5">
        <KeyboardShortcut combo="Esc" /> Close
      </span>
    </CommandPaletteFooter>
  </CommandPalette>
</template>

<style scoped>
/* The parts style themselves now that their source is scanned; this is the one
   place the palette wants to read tighter than the default — group headings
   closer to the rows they title. Styled through `data-slot`, per the library's
   contract; there are no class props to pass. */
.palette :deep([data-slot='command-palette-group']) {
  margin-top: 0.75rem;
  margin-bottom: 0.25rem;
}

.palette :deep([data-slot='command-palette-group-label']) {
  margin-bottom: 0.25rem;
  font-size: 0.75rem;
  line-height: 1rem;
}
</style>

