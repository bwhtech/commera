import { bootValue } from './boot.js'

// Filled by loadTranslations() before the app modules load, because their module-level labels call `__()`.
const messages = {}

// Frappe's `__(text, replacements, context)`: a string keyed `text:context` wins over the bare `text`,
// and an untranslated string falls back to the English source, so a missing entry never blanks a label.
export function createTranslator(translations) {
  return function __(text, replacements, context) {
    if (typeof text !== 'string' || !text) return text
    const translated = (context && translations[`${text}:${context}`]) || translations[text] || text
    return formatMessage(translated, replacements)
  }
}

export const __ = createTranslator(messages)

// Frappe's own endpoint, the one Desk uses: the version in the URL lets the browser cache it for a year.
export async function loadTranslations(fetchMessages = fetch) {
  const params = new URLSearchParams({ v: bootValue('translations_version', ''), lang: bootValue('lang', 'en') })
  try {
    const response = await fetchMessages(`/api/method/frappe.translate.get_boot_translations?${params}`, {
      credentials: 'same-origin',
    })
    Object.assign(messages, (await response.json()).message || {})
  } catch {
    // An unreachable dictionary leaves the shell in English rather than blank.
  }
}

// Templates reach `__` as a global property, the way Desk templates call `__()` with no import.
export const translation = {
  install(app) {
    app.config.globalProperties.__ = __
  },
}

// Arrays and numeric-keyed objects both fill `{0}`, as in Desk and the plugin kit before it.
function formatMessage(text, replacements) {
  if (!replacements || typeof replacements !== 'object') return text
  return text.replace(/\{(\d+)\}/g, (placeholder, index) => replacements[index] ?? placeholder)
}
