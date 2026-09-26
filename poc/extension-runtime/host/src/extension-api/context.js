import { inject } from 'vue'

// The key the host provides each extension's context under. It lives in this
// module, which the import map shares, so the host's provide() and an
// extension's inject() see the same Symbol. With two copies of this module
// (or of Vue) inject() returns undefined, which is exactly what the POC checks.
export const EXTENSION_CONTEXT = Symbol('commera-extension-context')

export function useExtension() {
  const context = inject(EXTENSION_CONTEXT, null)
  if (!context) {
    throw new Error('useExtension() called outside an extension slot')
  }
  return context
}
