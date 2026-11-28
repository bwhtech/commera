import { computed, onScopeDispose, shallowReactive, watch } from 'vue'

// Every dialog shell that is open, in the order it opened: the last one is on top.
const openLayers = shallowReactive([])

/**
 * Whether this dialog is covered by one opened over it: a "Discard changes?" over a form, a "New
 * collection" over Add product. `isOpen` is a ref or a getter.
 */
export function useDialogLayer(isOpen) {
  const layer = {}

  function leave() {
    const index = openLayers.indexOf(layer)
    if (index >= 0) openLayers.splice(index, 1)
  }

  watch(
    isOpen,
    (open) => {
      leave()
      if (open) openLayers.push(layer)
    },
    { immediate: true },
  )
  onScopeDispose(leave)

  return computed(() => {
    const index = openLayers.indexOf(layer)
    return index >= 0 && index < openLayers.length - 1
  })
}
