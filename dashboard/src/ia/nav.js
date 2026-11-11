import { isAdmin } from '../data/boot'
import { __ } from '../data/translation'
import { pluginNavItems } from './plugins'
import { search } from './search'

// The three reports. Home carries a live store's headline numbers, so none of
// them repeats them: each answers a question Home deliberately does not.
export const REPORTS = [
  { label: __('Revenue'), icon: 'lucide-banknote', to: '/analytics/revenue' },
  { label: __('Inventory'), icon: 'lucide-boxes', to: '/analytics/inventory' },
  { label: __('Storefront'), icon: 'lucide-globe', to: '/analytics/storefront' },
]

const ITEM = {
  home: { label: __('Home'), icon: 'lucide-house', to: '/' },
  search: {
    label: __('Search'),
    icon: 'lucide-search',
    shortcut: 'Mod+K',
    onClick: () => (search.open = true),
  },
  orders: { label: __('Orders'), icon: 'lucide-shopping-bag', to: '/orders' },
  customers: { label: __('Customers'), icon: 'lucide-users', to: '/customers' },
  discounts: { label: __('Discounts'), icon: 'lucide-badge-percent', to: '/discounts' },
  // A parent with children is a disclosure, not a destination: /analytics
  // itself holds nothing, so opening it lands on the first report.
  analytics: { label: __('Analytics'), icon: 'lucide-chart-line', to: '/analytics', children: REPORTS },
  products: { label: __('Products'), icon: 'lucide-package', to: '/products' },
  collections: { label: __('Collections'), icon: 'lucide-layers', to: '/collections' },
  attributes: { label: __('Attributes'), icon: 'lucide-tags', to: '/attributes' },
  theme: { label: __('Themes'), icon: 'lucide-palette', to: '/storefront/theme' },
  navigation: { label: __('Navigation'), icon: 'lucide-list-tree', to: '/storefront/navigation' },
  pages: { label: __('Pages'), icon: 'lucide-file-text', to: '/storefront/pages' },
  translations: { label: __('Translations'), icon: 'lucide-languages', to: '/storefront/translations' },
  reviews: { label: __('Reviews'), icon: 'lucide-star', to: '/reviews' },
}

// The daily work sits ungrouped at the top; the two groups below it are the
// things you go to on purpose. Neither collapses — three rows each is not
// enough to be worth hiding.
const coreSections = [
  {
    id: 'primary',
    items: [ITEM.home, ITEM.search, ITEM.orders, ITEM.customers, ITEM.discounts, ITEM.analytics],
  },
  { id: 'catalog', label: __('Catalog'), items: [ITEM.products, ITEM.collections, ITEM.attributes] },
  { id: 'storefront', label: __('Storefront'), items: [ITEM.theme, ITEM.navigation, ITEM.pages, ITEM.translations, ITEM.reviews] },
]

const pluginItems = pluginNavItems()

// Installed plugins sit in their own section after the core ones, which only shows when it has rows.
const pluginSections = pluginItems.length ? [{ id: 'plugins', label: __('Plugins'), items: pluginItems }] : []

export const sections = isAdmin ? [...coreSections, ...pluginSections] : pluginSections

// SidebarItem only infers active state from an exact route match, so a detail
// route (/products/p-2) would leave its section unlit. Resolve it here instead:
// the longest destination the current path sits under wins, which keeps
// /analytics/inventory on the report rather than on Analytics itself.
// Tools reached from a section, not listed in it, still belong to that section
// as far as the sidebar is concerned.
const ALIASES = {
  '/pricing': '/products',
  '/inventory': '/products',
  '/inventory/adjustments': '/products',
}

function flatten(items) {
  return items.flatMap((item) => [item, ...(item.children ?? [])])
}

export function activeNavTarget(path, groups = sections) {
  path = ALIASES[path] ?? path
  const targets = groups.flatMap((group) => flatten(group.items).map((item) => item.to)).filter(Boolean)
  return targets
    .filter((to) => (to === '/' ? path === '/' : path === to || path.startsWith(`${to}/`)))
    .sort((a, b) => b.length - a.length)[0]
}

// The product this dashboard is; the store it manages is named in Settings.
export const productName = 'Commera'
