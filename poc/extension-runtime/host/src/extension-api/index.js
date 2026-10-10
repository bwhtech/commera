// @commera/admin: everything an extension may import from the dashboard.
export { useExtension } from './context.js'
export { useMethodRead, useMethodAction } from './api.js'
export { default as ExtensionCard } from './ExtensionCard.vue'
export { CURATED_ICONS } from './icons.js'

export function money(amount, currency = 'USD') {
  return new Intl.NumberFormat('en', { style: 'currency', currency }).format(amount)
}
