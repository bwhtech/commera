import { h } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { bootValue } from '../data/boot'

// commera/www/commera.py has already filtered these for the session user, so the client only places them.
const plugins = bootValue('plugins', {}) ?? {}
const apps = plugins.apps ?? {}
const entries = plugins.entries ?? []

// An entry without `order` sorts after every ordered one, then by label, so two apps never shuffle.
function byOrder(left, right) {
  const leftOrder = left.order ?? Number.MAX_SAFE_INTEGER
  const rightOrder = right.order ?? Number.MAX_SAFE_INTEGER
  return leftOrder - rightOrder || String(left.label).localeCompare(String(right.label))
}

export function lucideIcon(name, fallback = 'blocks') {
  const icon = name || fallback
  return icon.startsWith('lucide-') ? icon : `lucide-${icon}`
}

export function appTitle(app) {
  return apps[app]?.title || app
}

// A logo is an SVG URL, so it travels as a component: frappe-ui's icon props and `Icon` take either kind.
const logoIcons = new Map()

function logoIcon(iconUrl) {
  if (!logoIcons.has(iconUrl)) logoIcons.set(iconUrl, () => h(AppIcon, { src: iconUrl }))
  return logoIcons.get(iconUrl)
}

// An app without its own logo borrows its first page's icon.
export function appIcon(app, iconUrl = apps[app]?.icon_url) {
  return iconUrl ? logoIcon(iconUrl) : lucideIcon(appPages(app)[0]?.icon)
}

// An entry's own icon wins; without one it wears its app's logo, then the place's generic icon.
export function pluginIcon(entry, fallback) {
  if (entry.icon) return lucideIcon(entry.icon)
  const iconUrl = apps[entry.app]?.icon_url
  return iconUrl ? logoIcon(iconUrl) : lucideIcon(null, fallback)
}

// Every app link resolves like an href against the app's root, so 'jobs/JOB-1', '../orders' and '/orders/X'
// mean the same from a page, a card and an action.
export function appLocation(app, to) {
  if (to.startsWith('/')) return to
  const resolved = new URL(to, `https://commera.invalid/plugins/${app}/`)
  return `${resolved.pathname.replace(/\/$/, '')}${resolved.search}${resolved.hash}`
}

export function pageRoute(entry) {
  return `/plugins/${entry.app}/${entry.name}`
}

export function placeEntries(place) {
  return entries.filter((entry) => entry.place === place).sort(byOrder)
}

function appPages(app) {
  return placeEntries('pages').filter((entry) => entry.app === app)
}

export function findPage(app, name) {
  return appPages(app).find((entry) => entry.name === name)
}

export function firstPageRoute(app) {
  const [first] = appPages(app)
  return first ? pageRoute(first) : null
}

function pageNavItem(entry) {
  return { label: entry.label, icon: pluginIcon(entry), to: pageRoute(entry) }
}

// One row per app: its only page, or a disclosure over its pages shaped like the Analytics row.
export function pluginNavItems() {
  const shown = placeEntries('pages').filter((entry) => entry.sidebar !== false)
  const byApp = new Map()
  for (const entry of shown) byApp.set(entry.app, [...(byApp.get(entry.app) ?? []), entry])
  return [...byApp.entries()]
    .map(([app, pages]) =>
      pages.length === 1
        ? { ...pageNavItem(pages[0]), icon: appIcon(app) }
        : {
            label: appTitle(app),
            icon: appIcon(app),
            to: `/plugins/${app}`,
            children: pages.map(pageNavItem),
          },
    )
    .sort((left, right) => left.label.localeCompare(right.label))
}

export function settingsTabValue(app) {
  return `plugin-${app}`
}

export function pluginSettingsTabs() {
  return placeEntries('settings').map((entry) => ({
    value: settingsTabValue(entry.app),
    label: entry.label,
    icon: pluginIcon(entry, 'settings'),
    keywords: [appTitle(entry.app).toLowerCase(), entry.app],
    entry,
  }))
}

function appKeywords(entry) {
  return [appTitle(entry.app).toLowerCase(), entry.app, ...(entry.keywords ?? [])]
}

// Every app page is a palette destination, sidebar or not, so an app never has to declare one twice.
export function pluginPageCommands() {
  return placeEntries('pages').map((entry) => ({
    id: `ext:${entry.key}`,
    label: entry.label,
    icon: pluginIcon(entry),
    keywords: appKeywords(entry),
    to: pageRoute(entry),
  }))
}

export function pluginCommands() {
  return placeEntries('commands').map((entry) => ({
    id: `ext:${entry.key}`,
    label: entry.label,
    icon: pluginIcon(entry, 'zap'),
    keywords: appKeywords(entry),
    appTitle: appTitle(entry.app),
    entry,
  }))
}

const PLACE_LABELS = {
  pages: 'Page',
  'order/cards': 'Order card',
  'product/cards': 'Product card',
  'customer/cards': 'Customer card',
  'order/actions': 'Order action',
  'product/actions': 'Product action',
  'customer/actions': 'Customer action',
  settings: 'Settings tab',
  commands: 'Command',
}

export function placeLabel(place) {
  return PLACE_LABELS[place] ?? place
}
