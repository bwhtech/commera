import { inject } from 'vue'

// The host provides and an app injects through these Symbols, so they must stay in a module the import map shares.
export const EXTENSION_CONTEXT = Symbol('commera-extension-context')
export const PAGE_CONTEXT = Symbol('commera-extension-page')
export const ACTION_CONTEXT = Symbol('commera-extension-action')
export const CARD_CONTEXT = Symbol('commera-extension-card')

export function __(text, replacements = []) {
  return String(text).replace(/\{(\d+)\}/g, (placeholder, index) => replacements[index] ?? placeholder)
}

function injectOrThrow(key, message) {
  const context = inject(key, null)
  if (!context) throw new Error(message)
  return context
}

export function useExtension() {
  return injectOrThrow(EXTENSION_CONTEXT, 'useExtension() was called outside a Commera app extension')
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
