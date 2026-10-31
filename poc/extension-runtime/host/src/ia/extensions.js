import { reactive } from 'vue'

// Stands in for boot.extensions (spec 2 §1.3): the server has already filtered
// by installed app, permission and condition, and stamped each module URL.
export const registry = reactive({ loaded: false, entries: [] })

export async function loadRegistry() {
  const response = await fetch('/api/extensions')
  registry.entries = await response.json()
  registry.loaded = true
}

export function extensionsFor(target) {
  return registry.entries.filter((entry) => entry.target === target)
}

export function navLinks() {
  return extensionsFor('admin.nav.link').map((entry) => ({
    label: entry.label,
    icon: `lucide-${entry.icon}`,
    to: entry.page ? `/apps/${entry.app}/${entry.page}` : entry.url,
  }))
}

export function appPage(app, page) {
  return extensionsFor('admin.app.page').find((entry) => entry.app === app && entry.page === page)
}
