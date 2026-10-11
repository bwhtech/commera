import './devBoot'

// commera/www/commera.py injects each boot key straight onto `window` (see
// commera.html's `window["{{ key }}"] = ...` loop) — csrf_token, date_format,
// time_format, lang, is_rtl, currency, currency_symbol. This is the one place
// that reads them back; no screen should reach into `window` itself.
export function bootValue(key, fallback) {
  const value = window[key]
  return typeof value === typeof fallback ? value : fallback
}

// The language cannot change without a round trip to the server, so these are
// read once rather than kept reactive — switching language reloads the shell,
// the way Frappe's own desk does.
export const language = bootValue('lang', 'en')
export const isRtl = bootValue('is_rtl', false)
export const direction = isRtl ? 'rtl' : 'ltr'

// frappe-ui ships Tailwind `rtl:` variants that only fire under a `dir` on an
// ancestor, so the mirroring for the whole shell hangs off this one attribute
// rather than a per-component flag.
export function applyDocumentDirection() {
  document.documentElement.dir = direction
  document.documentElement.lang = language
}
