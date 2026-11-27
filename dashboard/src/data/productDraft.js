// The product page edits a few fields in place and saves them with one Save, while every other
// section (photos, options, variant prices, stock) writes straight to the server and reloads the
// product. The draft is kept apart from that server answer, and a reload is folded in field by
// field: a field the merchant has not touched follows the server, a touched one keeps its edit.

const EMPTY_HTML = /^(<p>(<br\s*\/?>)?<\/p>)?$/

// The editor writes an empty description as `<p></p>` where the server stores null, and a number
// input hands back the text "25" for a stored 25: neither is an edit.
function normalizedValue(field, value) {
  if (field === 'collections') return [...(value ?? [])]
  if (field === 'description') return EMPTY_HTML.test(value ?? '') ? '' : value
  return value == null ? '' : String(value)
}

export function isSameValue(field, left, right) {
  return JSON.stringify(normalizedValue(field, left)) === JSON.stringify(normalizedValue(field, right))
}

export function storedDraft(product, fields) {
  return Object.fromEntries(fields.map((field) => [field, normalizedValue(field, product[field])]))
}

export function changedFields(draft, stored) {
  return Object.keys(stored).filter((field) => !isSameValue(field, draft[field], stored[field]))
}

export function rebaseDraft(draft, previousStored, nextStored) {
  return Object.fromEntries(
    Object.keys(nextStored).map((field) => [
      field,
      isSameValue(field, draft[field], previousStored[field]) ? normalizedValue(field, nextStored[field]) : draft[field],
    ]),
  )
}
