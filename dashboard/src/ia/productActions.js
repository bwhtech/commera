import { dialog, toast } from 'frappe-ui'
import { useAdminAction, trySubmit } from '../data/api'
import { __ } from '../data/translation'

// The product page's More actions: the secondary record actions only. Publishing sits in the
// page header, and every section of the page is already on screen, so nothing here jumps to one.
// The actions that need the loaded page (archive/restore, a reload after a write) arrive through
// `handlers`, so this module never touches the DOM or holds a copy of the request.

// Module scope, not per call: buildProductActions re-runs on every product
// reload, so a resource declared inside it would be rebuilt on every render.
const deleteAction = useAdminAction('catalog.delete_product')
const restockLevelAction = useAdminAction('catalog.set_restock_level')

// The storefront route lives per option. A live option is the one worth showing, but a draft
// one that already has a route still resolves for the merchant, so it is the fallback.
export function storefrontUrl(product) {
  const routed = product.variants.filter((variant) => variant.storefront_url)
  return (routed.find((variant) => variant.is_published) ?? routed[0])?.storefront_url ?? null
}

// The clipboard is refused outright over plain http and in some embedded
// browsers, so the link is put in front of the merchant to copy by hand.
export async function copyProductLink(url) {
  try {
    await navigator.clipboard.writeText(url)
    toast.success(__('Link copied'))
  } catch {
    toast.error(__('Could not copy the link'), { description: url })
  }
}

export function buildProductActions(product, router, handlers = {}) {
  const isArchived = product.status === 'archived'
  const isLive = product.variants.some((variant) => variant.is_published)
  const liveUrl = storefrontUrl(product)

  const groups = [
    {
      id: 'storefront',
      label: __('Store'),
      items: [
        // A product whose options have never been saved has no route, so both
        // rows are left out rather than offered and then apologised for.
        liveUrl && {
          key: 'preview',
          label: isLive ? __('View on store') : __('Preview on store'),
          icon: 'lucide-external-link',
          onClick: () => window.open(liveUrl, '_blank', 'noopener'),
        },
        liveUrl && {
          key: 'link',
          label: __('Copy link'),
          icon: 'lucide-link',
          onClick: () => copyProductLink(liveUrl),
        },
      ],
    },
    {
      id: 'inventory',
      label: __('Stock'),
      items: [
        {
          key: 'restock',
          label: __('Set the low-stock level'),
          icon: 'lucide-bell',
          onClick: () =>
            dialog.prompt({
              title: __('Set the low-stock level'),
              message: __(
                'Every size of this product reads as Low stock on the Stock screen at or below this number. Nobody is notified.',
              ),
              fields: [
                {
                  name: 'value',
                  label: __('Low-stock level'),
                  type: 'number',
                  required: true,
                  defaultValue: String(product.restock_level ?? ''),
                },
              ],
              onConfirm: async ({ values }) => {
                // set_restock_level stores cint(level), which truncates: 2.7 is kept as 2.
                // Truncating here too keeps the toast honest about what was stored.
                const level = Math.max(0, Math.trunc(Number(values.value) || 0))
                const saved = await trySubmit(restockLevelAction, { item_template: product.id, level })
                if (!saved) return

                toast.success(__('Low stock now reads at {0} or below', [level]))
                handlers.onReload?.()
              },
            }),
        },
      ],
    },
    {
      id: 'manage',
      label: __('Manage'),
      items: [
        {
          key: 'archive',
          label: isArchived ? __('Restore from archive') : __('Archive'),
          icon: isArchived ? 'lucide-archive-restore' : 'lucide-archive',
          // Restoring is undoable and goes straight through; archiving takes the product
          // off the storefront, so only that half asks first.
          onClick: () => {
            if (isArchived) {
              handlers.onToggleArchive()
              return
            }
            dialog.confirm({
              title: __('Archive this product?'),
              message: __('It leaves the storefront. Past orders keep their line items.'),
              theme: 'red',
              confirmLabel: __('Archive'),
              onConfirm: handlers.onToggleArchive,
            })
          },
        },
        {
          key: 'delete',
          label: __('Delete'),
          icon: 'lucide-trash-2',
          theme: 'red',
          onClick: () =>
            dialog.confirm({
              title: __('Delete {0}?', [product.title]),
              message: __(
                'This removes the product, its options and every size under it, for good. A product that has ever been ordered cannot be deleted. Archive it instead, and its past orders keep their line items.',
              ),
              theme: 'red',
              confirmLabel: __('Delete'),
              onConfirm: async () => {
                const deleted = await trySubmit(deleteAction, { item_template: product.id })
                if (!deleted) return
                toast.success(__('{0} deleted', [product.title]))
                router.push('/products')
              },
            }),
        },
      ],
    },
  ]
    .map((group) => ({ ...group, items: group.items.filter(Boolean) }))
    .filter((group) => group.items.length)

  return { groups }
}

// Dropdown wants a flat list with `group` separators, not our nested shape.
export function asDropdownOptions(groups) {
  return groups.map((group) => ({
    group: group.label,
    options: group.items.map(({ label, icon, onClick, theme }) => ({ label, icon, onClick, theme })),
  }))
}
