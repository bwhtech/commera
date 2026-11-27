import { __ } from './translation.js'

// Mirrors commera.api.admin.import_rows.FIELD_SYNONYMS and REQUIRED_FIELDS field for field.
export const TARGET_FIELDS = [
  { label: __("Don't import"), value: '' },
  { label: __('Product title'), value: 'title' },
  { label: __('Collection'), value: 'collection' },
  { label: __('Color'), value: 'color' },
  { label: __('Size'), value: 'size' },
  { label: __('Price'), value: 'sale_price' },
  { label: __('Original price'), value: 'compare_at_price' },
  { label: __('Stock'), value: 'stock' },
]

export const REQUIRED_FIELDS = ['title', 'sale_price']

export const fieldLabel = (field) => TARGET_FIELDS.find((target) => target.value === field)?.label ?? ''

// Collection is needed only when no collection is picked for every row instead.
export function missingFields(mapping, defaultCollection) {
  const required = defaultCollection ? REQUIRED_FIELDS : [...REQUIRED_FIELDS, 'collection']
  const mapped = new Set(Object.values(mapping))
  return required.filter((field) => !mapped.has(field))
}

// What the Map step still needs: the fields the mapping on screen lacks, plus any the last check of
// that same mapping reported, so a check the server answered "missing" can never unlock Continue.
export function stillNeeded(mapping, defaultCollection, checkedMissing = []) {
  return [...new Set([...missingFields(mapping, defaultCollection), ...checkedMissing])]
}

// "Use our suggestions" sends no mapping, so the server guesses again; the collection picked for every
// row still goes along, or a file without a collection column comes back with no rows checked.
export function suggestionParams(fileUrl, defaultCollection) {
  return defaultCollection ? { file_url: fileUrl, default_collection: defaultCollection } : { file_url: fileUrl }
}

// One column per field: picking a field another column already has moves it here, since the server
// would only ever read the first of the two.
export function remapColumn(mapping, header, field) {
  const next = { ...mapping }
  if (field) for (const [other, otherField] of Object.entries(next)) if (otherField === field) next[other] = ''
  next[header] = field
  return next
}

export function isSameMapping(first, second) {
  const keys = new Set([...Object.keys(first ?? {}), ...Object.keys(second ?? {})])
  return [...keys].every((key) => (first?.[key] ?? '') === (second?.[key] ?? ''))
}

// "1 KB" for a 200-byte file reads as rounding up; "0 KB" reads as empty.
export function fileSize(bytes) {
  if (bytes < 1024) return __('<1 KB')
  if (bytes < 1024 * 1024) return __('{0} KB', [Math.round(bytes / 1024)])
  return __('{0} MB', [(bytes / (1024 * 1024)).toFixed(1)])
}
