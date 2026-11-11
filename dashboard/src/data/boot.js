import { reactive } from 'vue'
import './devBoot.js'

// commera/www/commera.py puts each boot key on `window`. This is the one place
// that reads them back; no screen should reach into `window` itself.
export function bootValue(key, fallback) {
  // `globalThis` is `window` in a browser, and lets node unit tests import a module that reads boot.
  const value = globalThis[key]
  return typeof value === typeof fallback ? value : fallback
}

// Read once, not reactive: switching language reloads the shell, as Frappe's desk does.
export const language = bootValue('lang', 'en')
export const isRtl = bootValue('is_rtl', false)
export const direction = isRtl ? 'rtl' : 'ltr'
export const isAdmin = bootValue('is_admin', false)

// Every configured storefront language, default first: { code, name, endonym, direction }.
// Reactive, unlike the rest of boot: Settings › Languages changes it without a reload.
export const storefrontLanguages = reactive(bootValue('storefront_languages', []))
export const storefrontLanguageOptions = reactive(toLanguageOptions(storefrontLanguages))

// Replaced in place, so modules that imported the arrays keep reading the current list.
export function setStorefrontLanguages(languages) {
  storefrontLanguages.splice(0, storefrontLanguages.length, ...languages)
  storefrontLanguageOptions.splice(0, storefrontLanguageOptions.length, ...toLanguageOptions(languages))
}

function toLanguageOptions(languages) {
  return languages.map(({ code }) => ({ label: code.toUpperCase(), value: code }))
}

// Direction comes from Frappe's right-to-left set on the server, never from the code itself.
export function languageDirection(code) {
  return storefrontLanguages.find((language) => language.code === code)?.direction ?? 'ltr'
}

// frappe-ui's Tailwind `rtl:` variants fire only under a `dir` on an ancestor,
// so the whole shell mirrors off this one attribute.
export function applyDocumentDirection() {
  document.documentElement.dir = direction
  document.documentElement.lang = language
}
