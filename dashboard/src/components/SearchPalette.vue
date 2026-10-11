<script setup>
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon, KeyboardShortcut, useKeyboardShortcut } from 'frappe-ui'
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
import { SETTINGS_TABS, openSettings } from '../ia/settings'
import { search } from '../ia/search'
import { pluginCommands, pluginPageCommands } from '../ia/plugins'
import { customerRoute, orderRoute, productRoute } from '../ia/routes'
import { openImport } from '../data/importFlow'
import { openAddProduct } from '../data/addProduct'
import { confirmInstallDemoData } from '../data/demoData'
import { usePluginRun } from '../data/recordPlugins'

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

// `immediate: false`: the palette is always in the DOM, so an eager fetch would hit the backend
// on every page load. No debounce, matching Products.vue and Customers.vue.
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

// A hit list that is briefly empty mid-flight is not a miss: without this the palette flashes
// "nothing matches" between letters.
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

// Includes the screens the sidebar does not list but that are still real destinations.
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
  ...pluginPageCommands().map((page) => ({ ...page, run: () => router.push(page.to) })),
]

const CREATE = [
  { id: 'new-product', label: 'New product', icon: 'lucide-plus', keywords: ['add', 'create'], run: openAddProduct },
  { id: 'import', label: 'Import products from CSV', icon: 'lucide-upload', keywords: ['csv', 'bulk', 'shopify', 'migrate'], run: openImport },
  { id: 'receive', label: 'Receive stock', icon: 'lucide-package-plus', keywords: ['inward', 'grn'], run: () => router.push('/inventory') },
  { id: 'demo-data', label: 'Install demo data', icon: 'lucide-database', keywords: ['demo', 'sample', 'seed', 'example'], run: confirmInstallDemoData },
]

const SETTINGS = [
  { id: 'settings', label: 'Open settings', icon: 'lucide-settings', keywords: ['preferences', 'config'], run: () => openSettings() },
  ...SETTINGS_TABS.map((tab) => ({
    id: `settings-${tab.value}`,
    label: tab.label,
    icon: tab.icon,
    keywords: ['settings', ...tab.keywords],
    run: () => openSettings(tab.value),
  })),
]

const runPluginCommand = usePluginRun('plugins.run_command', (entry) => ({ key: entry.key }))

// The palette closes only after its select handler returns, so a confirm opened straight away would sit on a
// dialog that is about to close and lose focus with it.
async function startPlugin(entry) {
  await nextTick()
  return runPluginCommand(entry)
}

const PLUGINS = pluginCommands().map((command) => ({ ...command, suffix: command.appTitle, run: () => startPlugin(command.entry) }))

const ALL = [
  { label: 'Go to', commands: GO_TO },
  { label: 'Create', commands: CREATE },
  { label: 'Settings', commands: SETTINGS },
  { label: 'Plugins', commands: PLUGINS },
]

// Before you type, the palette is a short menu — the five destinations worth a
// shortcut. Dumping every command into an empty query is what made it a wall.
const SUGGESTED_SETTING_IDS = ['settings', 'settings-appearance', 'settings-payments']

const SUGGESTED = [
  { label: 'Jump to', commands: GO_TO.slice(0, 5) },
  { label: 'Create', commands: CREATE.slice(0, 2) },
  { label: 'Settings', commands: SETTINGS.filter((command) => SUGGESTED_SETTING_IDS.includes(command.id)) },
]

// The palette's own filter is off so the record rows can be ranked by hand;
// the command rows therefore have to filter here.
const commandGroups = computed(() => {
  if (!needle.value) return SUGGESTED
  // `needle` itself must stay as typed: it is the `search` param on four API calls
  // and the words quoted back in the empty state.
  const lowerNeedle = needle.value.toLowerCase()
  return ALL.map((group) => ({
    label: group.label,
    commands: group.commands.filter((command) =>
      [command.label, ...command.keywords].some((text) => text.toLowerCase().includes(lowerNeedle)),
    ),
  })).filter((group) => group.commands.length)
})

// Every id here is a real record name straight off the admin API — item_template, the Sales
// Order name, the Customer name — never a display string.
function onSelect(value) {
  if (value.kind === 'product') return router.push(productRoute(value.id))
  if (value.kind === 'order') return router.push(orderRoute(value.id))
  if (value.kind === 'customer') return router.push(customerRoute(value.id))
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

      <!-- Waits for a command group to sit under: with nothing at all, the palette reports
           empty itself through CommandPaletteEmpty below. -->
      <EmptyState v-if="noRecordHits && commandGroups.length" v-bind="noMatchState" />

      <CommandPaletteGroup v-for="group in commandGroups" :key="group.label" :label="group.label">
        <CommandPaletteItem
          v-for="command in group.commands"
          :key="command.id"
          :value="{ kind: 'command', id: command.id }"
        >
          <template #prefix>
            <Icon :name="command.icon" class="mr-2.5 size-4 shrink-0 text-ink-gray-5" />
          </template>
          {{ command.label }}
          <template v-if="command.suffix" #suffix>
            <span class="text-sm text-ink-gray-5">{{ command.suffix }}</span>
          </template>
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
/* Styled through `data-slot`, per the library's contract: there are no class props to pass. */
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

