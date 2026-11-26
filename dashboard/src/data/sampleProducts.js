import { ref } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { useAdminAction, trySubmit } from './api'
import { __ } from './translation'

export const loadSampleProductsAction = useAdminAction('sample_products.load_sample_products')
export const removeSampleProductsAction = useAdminAction('sample_products.remove_sample_products')

export const sampleProductsChanged = ref(0)

export async function loadSampleProducts() {
  if (loadSampleProductsAction.loading) return
  if (!(await trySubmit(loadSampleProductsAction))) return
  sampleProductsChanged.value += 1
  const count = loadSampleProductsAction.data.created.length
  toast.success(count === 1 ? __('1 demo product added') : __('{0} demo products added', [count]), {
    description: __('Remove them from Products when you add your own.'),
  })
}

export function confirmRemoveSampleProducts() {
  dialog.confirm({
    title: __('Remove demo products?'),
    message: __('This deletes only the demo products. Your own products stay as they are.'),
    theme: 'red',
    confirmLabel: __('Remove'),
    onConfirm: async () => {
      if (removeSampleProductsAction.loading) return
      if (!(await trySubmit(removeSampleProductsAction))) return
      sampleProductsChanged.value += 1
      const { removed, kept } = removeSampleProductsAction.data
      if (kept.length) {
        toast.warning(__('{0} demo products removed. {1} kept because they have orders or views', [removed.length, kept.length]))
        return
      }
      toast.success(__('Demo products removed'))
    },
  })
}
