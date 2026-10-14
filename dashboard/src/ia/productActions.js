import { dialog, toast } from 'frappe-ui'
import { useAdminAction } from '../data/api'
import { pickCollectionFor } from '../data/collections'

// Every action a merchant can take from a product page, grouped by intent.
// The `productActions` IA axis only changes where these are rendered — the set
// itself stays the same, so the variants stay comparable.
//
// Every row reaches a real endpoint. The ones that need the loaded page —
// publish/unpublish, archive/restore, a reload after a write, and the three
// "jump to a section" rows — arrive through `handlers`, so this module never
// touches the DOM or holds a copy of the request.

// Module scope, not per call: buildProductActions re-runs on every product
// reload, so a resource declared inside it would be rebuilt on every render.
const deleteAction = useAdminAction('catalog.delete_product')
const receiveStockAction = useAdminAction('inventory.receive_stock')
const restockLevelAction = useAdminAction('catalog.set_restock_level')

// The storefront route lives per option, and only a published option is worth
// showing off — but an unpublished one that already has a route still resolves,
// so it is a usable fallback rather than nothing.
function storefrontUrl(product) {
  const routed = product.variants.filter((variant) => variant.storefront_url)
  return (routed.find((variant) => variant.is_published) ?? routed[0])?.storefront_url ?? null
}

function sizeItemCodes(product) {
  return product.variants.flatMap((variant) => variant.sizes.map((size) => size.item_code)).filter(Boolean)
}

export function buildProductActions(product, router, handlers = {}) {
  const isArchived = product.status === 'archived'
  const isPublished = product.variants.some((variant) => variant.is_published)
  const liveUrl = storefrontUrl(product)
  const itemCodes = sizeItemCodes(product)

  const publish = {
    key: 'publish',
    label: isPublished ? 'Unpublish' : 'Publish to storefront',
    icon: isPublished ? 'lucide-eye-off' : 'lucide-globe',
    onClick: handlers.onTogglePublish,
  }

  const groups = [
    {
      id: 'storefront',
      label: 'Storefront',
      items: [
        publish,
        // Both rows need a route to point at; a product whose options have
        // never been published has none, so they are left out rather than
        // offered and then apologised for.
        liveUrl && {
          key: 'preview',
          label: 'Preview on storefront',
          icon: 'lucide-external-link',
          onClick: () => window.open(liveUrl, '_blank', 'noopener'),
        },
        liveUrl && {
          key: 'link',
          label: 'Copy product link',
          icon: 'lucide-link',
          // The clipboard is refused outright over plain http and in some embedded
          // browsers, so the link is put in front of the merchant to copy by hand.
          onClick: async () => {
            try {
              await navigator.clipboard.writeText(liveUrl)
              toast.success('Link copied')
            } catch {
              toast.error('Could not copy the link', { description: liveUrl })
            }
          },
        },
        // Named for what the section holds: the generated per-option addresses, read-only.
        // commera has no per-product SEO field to edit, here or in Desk.
        {
          key: 'seo',
          label: 'See storefront addresses',
          icon: 'lucide-link',
          onClick: () => handlers.onScrollTo?.('product-storefront'),
        },
      ],
    },
    {
      id: 'catalogue',
      label: 'Catalogue',
      items: [
        // The axis is fixed at creation and no endpoint adds another, so the section it
        // scrolls to only names the one this product has — the row says exactly that.
        {
          key: 'option',
          label: 'See options',
          icon: 'lucide-git-branch',
          onClick: () => handlers.onScrollTo?.('product-options'),
        },
        {
          key: 'bulk',
          label: 'Bulk edit variants',
          icon: 'lucide-table-2',
          onClick: () => handlers.onScrollTo?.('product-variants'),
        },
        {
          key: 'collection',
          label: 'Add to collection',
          icon: 'lucide-layers',
          onClick: () =>
            pickCollectionFor([product.id], {
              label: product.title,
              currentCollection: product.collection ?? '',
              onDone: handlers.onReload,
            }),
        },
      ],
    },
    {
      id: 'inventory',
      label: 'Inventory',
      items: [
        // Same operation as the Stock screen's "Adjust quantity", so it is
        // worded the same: commera only exposes an additive receipt, there is
        // no reason-coded adjustment and no "set on-hand to X".
        itemCodes.length && {
          key: 'adjust',
          label: 'Receive stock',
          icon: 'lucide-package-plus',
          onClick: () =>
            dialog.prompt({
              title: `Receive stock on ${product.title}`,
              message: `Adds this quantity to each of the ${itemCodes.length} sizes under this product. There is no way to set stock to an exact number here.`,
              fields: [{ name: 'value', label: 'Quantity received', type: 'number', required: true }],
              onConfirm: async ({ values }) => {
                const quantity = Math.max(0, Number(values.value) || 0)
                if (!quantity) return

                try {
                  await receiveStockAction.submit({
                    received_quantities: Object.fromEntries(itemCodes.map((code) => [code, quantity])),
                  })
                } catch {
                  return
                }

                toast.success(`Received ${quantity} on ${itemCodes.length} sizes`)
                handlers.onReload?.()
              },
            }),
        },
        {
          key: 'restock',
          label: 'Set the low-stock level',
          icon: 'lucide-bell',
          onClick: () =>
            dialog.prompt({
              title: 'Set the low-stock level',
              message:
                'Every size of this product reads as Low stock on the Stock screen at or below this number. Nobody is notified.',
              fields: [
                {
                  name: 'value',
                  label: 'Low-stock level',
                  type: 'number',
                  required: true,
                  defaultValue: String(product.restock_level ?? ''),
                },
              ],
              onConfirm: async ({ values }) => {
                // set_restock_level stores cint(level), which truncates: 2.7 is kept as 2.
                // Truncating here too keeps the toast honest about what was stored.
                const level = Math.max(0, Math.trunc(Number(values.value) || 0))
                try {
                  await restockLevelAction.submit({ item_template: product.id, level })
                } catch {
                  return
                }

                toast.success(`Low stock now reads at ${level} or below`)
                handlers.onReload?.()
              },
            }),
        },
      ],
    },
    {
      id: 'pricing',
      label: 'Pricing',
      items: [
        { key: 'price', label: 'Bulk edit prices across products', icon: 'lucide-indian-rupee', onClick: () => router.push('/pricing') },
      ],
    },
    {
      id: 'insight',
      label: 'Reporting',
      items: [
        // orders.get_orders searches order name and customer name only — there is no
        // product filter to send, so the row promises no more than the trip it makes.
        { key: 'orders', label: 'Open the orders list', icon: 'lucide-shopping-bag', onClick: () => router.push('/orders') },
      ],
    },
    {
      id: 'manage',
      label: 'Manage',
      items: [
        {
          key: 'archive',
          label: isArchived ? 'Restore from archive' : 'Archive',
          icon: isArchived ? 'lucide-archive-restore' : 'lucide-archive',
          // Restoring is undoable and goes straight through; archiving takes the product
          // off the storefront, so only that half asks first.
          onClick: () => {
            if (isArchived) {
              handlers.onToggleArchive()
              return
            }
            dialog.confirm({
              title: 'Archive this product?',
              message: 'It leaves the storefront. Past orders keep their line items.',
              theme: 'red',
              confirmLabel: 'Archive',
              onConfirm: handlers.onToggleArchive,
            })
          },
        },
        {
          key: 'delete',
          label: 'Delete',
          icon: 'lucide-trash-2',
          theme: 'red',
          onClick: () =>
            dialog.confirm({
              title: `Delete ${product.title}?`,
              message:
                'This removes the product, its options and every size under it, for good. A product that has ever been ordered cannot be deleted — archive it instead, and its past orders keep their line items.',
              theme: 'red',
              confirmLabel: 'Delete',
              onConfirm: async () => {
                try {
                  await deleteAction.submit({ item_template: product.id })
                } catch {
                  return
                }
                toast.success(`${product.title} deleted`)
                router.push('/products')
              },
            }),
        },
      ],
    },
  ].map((group) => ({ ...group, items: group.items.filter(Boolean) }))

  // Look an action up by key instead of a group/index pair, so removing or
  // reordering entries above can't silently point `quick` at the wrong one.
  const findAction = (key) => groups.flatMap((group) => group.items).find((item) => item.key === key)

  // The handful worth surfacing without opening a menu. A product with no
  // sizes yet has no Receive stock row, so the list is filtered, not padded.
  const quick = [publish, findAction('adjust'), findAction('price'), findAction('bulk')].filter(Boolean)

  return { groups, quick }
}

// Dropdown wants a flat list with `group` separators, not our nested shape.
export function asDropdownOptions(groups) {
  return groups.map((group) => ({
    group: group.label,
    options: group.items.map(({ label, icon, onClick, theme }) => ({ label, icon, onClick, theme })),
  }))
}
