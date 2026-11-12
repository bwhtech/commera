import { __ } from './translation.js'

// Kept apart from the server calls in translations.js, so these test without frappe-ui.

// The registry gives a type and a label; where it sits in the picker and its icon are the
// dashboard's. A plugin's own resource lands in Other.
const RESOURCE_PLACES = {
  product: { group: 'catalog', icon: 'lucide-tag', one: __('Product') },
  collection: { group: 'catalog', icon: 'lucide-folder', one: __('Collection') },
  page: { group: 'storefront', icon: 'lucide-file-text', one: __('Page') },
  theme_section: { group: 'storefront', icon: 'lucide-palette', one: __('Theme section') },
  landing_page: { group: 'storefront', icon: 'lucide-image', one: __('Landing page') },
  footer_section: { group: 'navigation', icon: 'lucide-panel-bottom', one: __('Footer section') },
  footer_link: { group: 'navigation', icon: 'lucide-link', one: __('Footer link') },
  shop: { group: 'settings', icon: 'lucide-store', one: __('Shop') },
}

const RESOURCE_GROUPS = [
  { key: 'catalog', label: __('Catalog') },
  { key: 'storefront', label: __('Storefront') },
  { key: 'navigation', label: __('Navigation') },
  { key: 'settings', label: __('Settings') },
  { key: 'other', label: __('Other') },
]

export function describeResource(resource) {
  const place = RESOURCE_PLACES[resource.type] ?? { group: 'other', icon: 'lucide-box', one: resource.label }
  return { ...resource, ...place }
}

// Registry order within a group, the groups in picker order, empty groups left out.
export function groupResources(resources) {
  const described = resources.map(describeResource)
  return RESOURCE_GROUPS.map((group) => ({
    ...group,
    resources: described.filter((resource) => resource.group === group.key),
  })).filter((group) => group.resources.length)
}

// Search engine fields share one card on every resource, and images another.
export function sectionOf(field, resourceLabel) {
  if (field.kind === 'image') return __('Media')
  if (field.field.startsWith('meta_')) return __('Search engine listing')
  return resourceLabel
}

export function groupSections(fields, resourceLabel) {
  const sections = new Map()
  for (const field of fields) {
    const title = sectionOf(field, resourceLabel)
    sections.set(title, [...(sections.get(title) ?? []), field])
  }
  return [...sections].map(([title, sectionFields]) => ({ title, fields: sectionFields }))
}

export function toDoCount(counts) {
  return counts.missing + counts.outdated
}

// A resource with no source text at all has nothing to translate, which is not the same as done.
export function isEmptyResource(counts) {
  return !counts.missing && !counts.outdated && !counts.current
}

// A record as it will be once saved: an unsaved value is done, unless it clears a text field.
export function itemProgress(item, pending, language, resource) {
  const progress = { toDo: 0, outdated: false, unsaved: 0 }
  for (const field of item.fields) {
    const value = pending[fieldKey(language, resource, item.name, field.field)]
    if (value !== undefined) {
      progress.unsaved += 1
      if (!value && field.kind !== 'image' && !field.source_empty) progress.toDo += 1
    } else if (field.status !== 'current') {
      progress.toDo += 1
      progress.outdated ||= field.status === 'outdated'
    }
  }
  return progress
}

// The status dot of a record in the list: unsaved edits first, then what is left to do.
export function progressStatus(progress) {
  if (progress.unsaved) return 'unsaved'
  if (progress.toDo) return progress.outdated ? 'outdated' : 'missing'
  return 'current'
}

// The editor's language menu: each target language with its to-do count, a hidden one marked.
export function languageChoices(languages, counts) {
  return languages.map((language) => ({
    code: language.code,
    label: __('{0} · {1} to do', [language.name, toDoCount(languageTotals(counts[language.code]))]),
    hidden: !language.published,
  }))
}

// Every resource of one language added up, for its card and the editor's language menu.
export function languageTotals(languageCounts = {}) {
  const totals = { missing: 0, outdated: 0, current: 0 }
  for (const counts of Object.values(languageCounts)) {
    for (const status of Object.keys(totals)) totals[status] += counts[status]
  }
  const all = totals.missing + totals.outdated + totals.current
  // Nothing to translate yet counts as done, not as 0%.
  return { ...totals, percent: all ? Math.floor((totals.current / all) * 100) : 100 }
}

// A key per field across languages, records and resources, so unsaved edits survive switching items.
export function fieldKey(language, resource, name, field) {
  return JSON.stringify([language, resource, name, field])
}

export function parseFieldKey(key) {
  const [language, resource, name, field] = JSON.parse(key)
  return { language, resource, name, field }
}
