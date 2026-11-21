// Commera sits on top of ERPNext. Company, tax and accounting records live
// there and are read-only here — the merchant never has to learn ERPNext, but
// where the full record matters we hand off to it rather than re-implement it.
// Commera runs ON the ERPNext site, so every handoff below is same-origin: a
// path, never a host.

export function erpnextLink(doctype, name) {
  const slug = doctype.toLowerCase().replace(/\s+/g, '-')
  return `/app/${slug}/${encodeURIComponent(name)}`
}

// Frappe's own PDF endpoints, opened as a link the way the Desk list view does.
// NOTE: download_multi_pdf is gated on the User.bulk_actions permission, so a
// shop owner without it gets Frappe's error page in the new tab, not a toast —
// there is no way to know before opening it.
export function printUrl(doctype, names, format) {
  const single = names.length === 1
  const params = new URLSearchParams(
    single ? { doctype, name: names[0] } : { doctype, name: JSON.stringify(names) },
  )
  if (format) params.set('format', format)
  const method = single
    ? 'frappe.utils.print_format.download_pdf'
    : 'frappe.utils.print_format.download_multi_pdf'
  return `/api/method/${method}?${params}`
}
