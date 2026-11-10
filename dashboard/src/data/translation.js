import { bootValue } from './boot.js'

// Frappe's `__(text, replacements, context)`: a string keyed `text:context` wins over the bare `text`,
// and an untranslated string falls back to the English source, so a missing entry never blanks a label.
export function createTranslator(messages) {
  return function __(text, replacements, context) {
    if (typeof text !== 'string' || !text) return text
    const translated = (context && messages[`${text}:${context}`]) || messages[text] || text
    return formatMessage(translated, replacements)
  }
}

// Built once at import: module-level labels (nav, settings tabs) call `__()` as their module loads.
export const __ = createTranslator(bootValue('translations', {}))

// Templates reach `__` as a global property, the way Desk templates call `__()` with no import.
export const translation = {
  install(app) {
    app.config.globalProperties.__ = __
  },
}

function formatMessage(text, replacements) {
  if (!Array.isArray(replacements)) return text
  return text.replace(/\{(\d+)\}/g, (placeholder, index) => replacements[index] ?? placeholder)
}
