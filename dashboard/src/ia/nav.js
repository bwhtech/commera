import { appNavItems } from './extensions'
import { search } from './search'

// The three reports. Overview carries the headline numbers, so none of them
// repeats it: each answers a question the dashboard deliberately does not.
export const REPORTS = [
  { label: 'Revenue', icon: 'lucide-banknote', to: '/analytics/revenue' },
  { label: 'Inventory', icon: 'lucide-boxes', to: '/analytics/inventory' },
  { label: 'Storefront', icon: 'lucide-globe', to: '/analytics/storefront' },
]

const ITEM = {
  overview: { label: 'Overview', icon: 'lucide-layout-dashboard', to: '/' },
  search: {
    label: 'Search',
    icon: 'lucide-search',
    shortcut: 'Mod+K',
    onClick: () => (search.open = true),
  },
  orders: { label: 'Orders', icon: 'lucide-shopping-bag', to: '/orders' },
  customers: { label: 'Customers', icon: 'lucide-users', to: '/customers' },
  // A parent with children is a disclosure, not a destination: /analytics
  // itself holds nothing, so opening it lands on the first report.
  analytics: { label: 'Analytics', icon: 'lucide-chart-line', to: '/analytics', children: REPORTS },
  products: { label: 'Products', icon: 'lucide-package', to: '/products' },
  collections: { label: 'Collections', icon: 'lucide-layers', to: '/collections' },
  attributes: { label: 'Attributes', icon: 'lucide-tags', to: '/attributes' },
  theme: { label: 'Theme', icon: 'lucide-palette', to: '/storefront/theme' },
  navigation: { label: 'Navigation', icon: 'lucide-list-tree', to: '/storefront/navigation' },
  pages: { label: 'Pages', icon: 'lucide-file-text', to: '/storefront/pages' },
  reviews: { label: 'Reviews', icon: 'lucide-star', to: '/reviews' },
}

// The daily work sits ungrouped at the top; the two groups below it are the
// things you go to on purpose. Neither collapses — three rows each is not
// enough to be worth hiding.
const coreSections = [
  {
    id: 'primary',
    items: [ITEM.overview, ITEM.search, ITEM.orders, ITEM.customers, ITEM.analytics],
  },
  { id: 'catalog', label: 'Catalog', items: [ITEM.products, ITEM.collections, ITEM.attributes] },
  { id: 'storefront', label: 'Storefront', items: [ITEM.theme, ITEM.navigation, ITEM.pages, ITEM.reviews] },
]

const appItems = appNavItems()

// Installed apps sit in their own section after the core ones, which only shows when it has rows.
export const sections = [...coreSections, ...(appItems.length ? [{ id: 'apps', label: 'Apps', items: appItems }] : [])]

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
