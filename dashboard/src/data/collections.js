// The collection picker is offered from two places — one product's ⋯ menu and the Products bulk
// bar — so the list, the wording and the count it reports live here rather than in each screen.
import { computed } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead } from './api'

// Module scope: the product action list is rebuilt on every product reload, and a resource per
// rebuild would refetch the collection list each time.
const collectionsRequest = useAdminRead('catalog.get_collections', { immediate: false })
const collectionAction = useAdminAction('catalog.add_products_to_collection')

const collectionOptions = computed(() =>
  (collectionsRequest.data ?? []).map((name) => ({ label: name, value: name })),
)

export function useCollections() {
  return {
    collectionOptions,
    loading: collectionAction.loading,
    load: () => collectionsRequest.fetch(),
  }
}

function productWord(total) {
  return `${total} product${total === 1 ? '' : 's'}`
}

// `label` names what is being filed — one product's title, or "3 products" from a selection.
export async function pickCollectionFor(itemTemplates, { label, currentCollection = '', onDone } = {}) {
  if (!itemTemplates.length) return

  await collectionsRequest.fetch()
  if (collectionsRequest.error) return
  if (!collectionOptions.value.length) {
    toast.info('There are no collections yet — create one first.')
    return
  }

  dialog.prompt({
    title: `File ${label} under a collection`,
    message: 'A product sits in one collection, so this replaces the one it is in now.',
    fields: [
      {
        name: 'collection',
        label: 'Collection',
        type: 'select',
        required: true,
        defaultValue: currentCollection,
        options: collectionOptions.value,
      },
    ],
    confirmLabel: 'Move',
    onConfirm: async ({ values }) => {
      let response
      try {
        response = await collectionAction.submit({
          item_templates: itemTemplates,
          collection: values.collection,
        })
      } catch {
        return
      }

      // The server reports which products it actually saved, and under which collection it
      // resolved the name to — the toast says that, not what was asked for.
      toast.success(`${productWord(response.updated.length)} moved to ${response.collection}`)
      onDone?.()
    },
  })
}
