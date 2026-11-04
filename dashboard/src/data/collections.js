// The collection picker is offered from two places — one product's ⋯ menu and the Products bulk
// bar — so the list, the wording and the count it reports live here rather than in each screen.
import { computed } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead, trySubmit } from './api'
import { __ } from './translation'

// Module scope: the product action list is rebuilt on every product reload, and a resource per
// rebuild would refetch the collection list each time.
const collectionsRequest = useAdminRead('catalog.get_collections', { immediate: false })
const addAction = useAdminAction('catalog.add_products_to_collection')
const removeAction = useAdminAction('catalog.remove_products_from_collection')

const collectionOptions = computed(() =>
  (collectionsRequest.data ?? []).map((name) => ({ label: name, value: name })),
)

export function useCollections() {
  return {
    collectionOptions,
    loading: computed(() => addAction.loading || removeAction.loading),
    load: () => collectionsRequest.fetch(),
  }
}

function productWord(total) {
  return total === 1 ? __('1 product') : __('{0} products', [total])
}

// A product sits in several collections, so the picker either adds one or takes one away; the
// server refuses to take away a product's last collection. The wording is in functions, so it is
// translated when the picker opens, not at import.
const MODES = {
  add: {
    action: addAction,
    title: (label) => __('Add {0} to a collection', [label]),
    message: () => __('Products keep the collections they are already in.'),
    confirmLabel: () => __('Add'),
    done: (count, collection) => __('{0} added to {1}', [productWord(count), collection]),
  },
  remove: {
    action: removeAction,
    title: (label) => __('Remove {0} from a collection', [label]),
    message: () => __('A product must stay in at least one collection.'),
    confirmLabel: () => __('Remove'),
    done: (count, collection) => __('{0} removed from {1}', [productWord(count), collection]),
  },
}

// `label` names what is being filed — one product's title, or "3 products" from a selection.
export async function pickCollectionFor(itemTemplates, { label, mode = 'add', onDone } = {}) {
  if (!itemTemplates.length) return

  await collectionsRequest.fetch()
  if (collectionsRequest.error) return
  if (!collectionOptions.value.length) {
    toast.info(__('There are no collections yet — create one first.'))
    return
  }

  const { action, title, message, confirmLabel, done } = MODES[mode]
  dialog.prompt({
    title: title(label),
    message: message(),
    fields: [
      {
        name: 'collection',
        label: __('Collection'),
        type: 'select',
        required: true,
        options: collectionOptions.value,
      },
    ],
    confirmLabel: confirmLabel(),
    onConfirm: async ({ values }) => {
      const changed = await trySubmit(action, {
        item_templates: itemTemplates,
        collection: values.collection,
      })
      if (!changed) return
      const response = action.data

      // The server reports which products it actually changed (one already in the collection is
      // skipped), and under which collection it resolved the name to — the toast says that.
      toast.success(done(response.updated.length, response.collection))
      onDone?.()
    },
  })
}
