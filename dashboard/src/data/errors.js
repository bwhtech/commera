import { __ } from './translation'

// Frappe prefixes every thrown message with its exception class, which is for
// a traceback, not for a shop owner.
export function errorMessage(error, fallback = __('Something went wrong')) {
  // Frappe marks up method names with <strong>, which a screen renders as text rather than as bold.
  const message = error?.message
    ?.replace(/^\s*[A-Za-z]*Error:\s*/, '')
    .replace(/<[^>]+>/g, '')
    .trim()
  return message || fallback
}
