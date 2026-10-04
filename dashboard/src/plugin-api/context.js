import { inject } from 'vue'

// The host provides and an app injects through these Symbols, so they must stay in a module the import map shares.
export const PLUGIN_CONTEXT = Symbol('commera-plugin-context')
export const PAGE_CONTEXT = Symbol('commera-plugin-page')
export const ACTION_CONTEXT = Symbol('commera-plugin-action')
export const CARD_CONTEXT = Symbol('commera-plugin-card')

export function __(text, replacements = []) {
  return String(text).replace(/\{(\d+)\}/g, (placeholder, index) => replacements[index] ?? placeholder)
}

function injectOrThrow(key, message) {
  const context = inject(key, null)
  if (!context) throw new Error(message)
  return context
}

export function usePlugin() {
  return injectOrThrow(PLUGIN_CONTEXT, 'usePlugin() was called outside a Commera plugin')
}

export function usePage() {
  return injectOrThrow(PAGE_CONTEXT, 'usePage() only works in a page (commera/pages/<name>/index.vue)')
}

export function useAction() {
  return injectOrThrow(ACTION_CONTEXT, 'useAction() only works in an action (commera/<record>/actions/<name>/index.vue)')
}

export function useCard() {
  return injectOrThrow(CARD_CONTEXT, 'useCard() only works in a card (commera/<record>/cards/<name>/index.vue)')
}
