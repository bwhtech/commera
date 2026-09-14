<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, Dropdown, dialog, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import Thumb from './Thumb.vue'
import EditableValue from './EditableValue.vue'
import EmptyState from './EmptyState.vue'
import VariantDialog from './VariantDialog.vue'
import { useAdminAction } from '../data/api'
import { stockTone } from '../data/format'
import { pricePayload, shownPrice } from '../data/product'
import { ia } from '../ia/store'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])

const selection = ref([])

// A row opens the variant rather than navigating: a variant is a small record,
// and you are usually working down the matrix, not away from it.
const editing = ref(null)
const showVariant = ref(false)

function openVariant(variant) {
  editing.value = variant
  showVariant.value = true
}

// Every real option (Style Attribute Variant) already carries its own single
// attribute value — Color, say — set at product creation. commera has no
// endpoint to add a further axis to an existing product (create_product only
// takes option_attribute/size_attribute once, at insert), so unlike the
// prototype's options[] this list is read-only: it names the one axis this
// product already has and shows its values, nothing more.
const optionValues = computed(() => [...new Set(props.product.variants.map((v) => v.option))])

const priceAction = useAdminAction('catalog.set_variant_price')

async function setPrice(variant, rate) {
  await priceAction.submit({
    style_attribute_variant: variant.name,
    ...pricePayload(variant.sizes[0], rate),
  })
  if (priceAction.error) return
  toast.success(`Price updated for ${variant.option} (${variant.sizes.length} sizes)`)
  emit('saved')
}

async function bulkSetPrice() {
  const selected = props.product.variants.filter((variant) => selection.value.includes(variant.name))
  if (!selected.length) return

  dialog.prompt({
    title: `Set price on ${selected.length} ${selected.length === 1 ? 'variant' : 'variants'}`,
    message: 'Sets the price for every size under each selected variant.',
    fields: [{ name: 'value', label: 'Price', type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const rate = Math.max(0, Number(values.value) || 0)
      for (const variant of selected) {
        await priceAction.submit({
          style_attribute_variant: variant.name,
          ...pricePayload(variant.sizes[0], rate),
        })
        // A failure already toasted inside useAdminAction — stop rather than reprice the rest silently.
        if (priceAction.error) return
      }
      selection.value = []
      toast.success(`Price updated on ${selected.length} ${selected.length === 1 ? 'variant' : 'variants'}`)
      emit('saved')
    },
  })
}

const publishAction = useAdminAction('catalog.set_variant_published')
const receiveAction = useAdminAction('inventory.receive_stock')

// The server refuses to publish an option with no photo or no size, and says so. Reading the
// same blockers off the row means the matrix can say it before the merchant clicks.
function publishBlockers(variant) {
  return variant.blockers ?? []
}

async function togglePublish(variant) {
  await publishAction.submit({ style_attribute_variant: variant.name, publish: variant.is_published ? 0 : 1 })
  // A refusal names the missing photo or size and has already been toasted.
  if (publishAction.error) return
  toast.success(variant.is_published ? `${variant.option} hidden from the storefront` : `${variant.option} published`)
  emit('saved')
}

// Same additive receipt as the Stock screen and the product menu — commera has no way to set
// on-hand to an exact number, so one quantity goes onto every size of this option.
function receiveStock(variant) {
  const itemCodes = variant.sizes.map((size) => size.item_code).filter(Boolean)
  if (!itemCodes.length) {
    toast.info(`${variant.option} has no sizes to receive stock against yet.`)
    return
  }

  dialog.prompt({
    title: `Receive stock on ${variant.option}`,
    message: `Adds this quantity to each of the ${itemCodes.length} sizes under this option. There is no way to set stock to an exact number here.`,
    fields: [{ name: 'value', label: 'Quantity received', type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const quantity = Math.max(0, Math.trunc(Number(values.value) || 0))
      if (!quantity) return

      await receiveAction.submit({
        received_quantities: Object.fromEntries(itemCodes.map((code) => [code, quantity])),
      })
      if (receiveAction.error) return
      toast.success(`Received ${quantity} on ${itemCodes.length} sizes`)
      emit('saved')
    },
  })
}

function rowActions(variant) {
  return [
    {
      label: variant.is_published ? 'Hide from storefront' : 'Publish to storefront',
      icon: variant.is_published ? 'lucide-eye-off' : 'lucide-globe',
      onClick: () => togglePublish(variant),
    },
    { label: 'Receive stock', icon: 'lucide-package-plus', onClick: () => receiveStock(variant) },
    { label: 'Open full page', icon: 'lucide-external-link', onClick: () => openVariant(variant) },
  ]
}

// Seven columns. The min-width has to clear every fixed column plus both minmax floors, or the
// 1.3fr Variant column collapses to nothing instead of the row scrolling.
const columns = ['minmax(7rem,1.3fr)', 'minmax(5rem,1fr)', '6.5rem', '5rem', '4.5rem', '7rem', '3rem']
</script>

<template>
  <section class="space-y-5">
    <!-- The axis, first: the matrix below is nothing but its values. -->
    <div id="product-options" class="rounded-5 border border-outline-gray-1">
      <div class="px-4 py-3">
        <h2 class="text-lg-semibold text-ink-gray-8">Options</h2>
        <p class="mt-1 text-p-sm text-ink-gray-5">{{ product.option_attribute ?? 'Option' }}, set at creation.</p>
      </div>

      <div v-if="optionValues.length" class="border-t border-outline-gray-1 px-4 py-3">
        <div class="flex items-start gap-3">
          <span class="w-24 shrink-0 pt-0.5 text-base text-ink-gray-6">{{ product.option_attribute }}</span>
          <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <Badge v-for="value in optionValues" :key="value" :label="value" variant="subtle" />
          </div>
        </div>
      </div>

      <div v-else class="border-t border-outline-gray-1 px-4 py-6 text-center">
        <p class="text-base text-ink-gray-7">This product has no options</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">It sells as a single item.</p>
      </div>
    </div>

    <!-- The matrix: one row per option, each with its own sizes underneath. The
         card, its List and its headers stay mounted with no variants — the ⋯
         menu's "jump to variants" row scrolls to this id and would land nowhere
         if the card came and went, and an empty column layout is how every other
         list in the app answers "no rows" (see ProductStock right below). -->
    <div id="product-variants" class="rounded-5 border border-outline-gray-1">
      <div class="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <h2 class="text-lg-semibold text-ink-gray-8">Variants</h2>
        <div class="flex items-center gap-2">
          <template v-if="selection.length">
            <span class="text-sm text-ink-gray-5">{{ selection.length }} selected</span>
            <Button label="Set price" @click="bulkSetPrice" />
            <Button label="Clear" variant="ghost" @click="selection = []" />
          </template>
        </div>
      </div>

      <div class="overflow-x-auto px-2 pb-2">
        <List
          v-model:selection="selection"
          class="min-w-[42rem]"
          selectable
          :row-height="Math.max(ia.density, 48)"
          :columns="columns"
        >
          <ListHeader>
            <ListHeaderCell>Variant</ListHeaderCell>
            <ListHeaderCell>Sizes</ListHeaderCell>
            <ListHeaderCell>Price</ListHeaderCell>
            <ListHeaderCell>Stock</ListHeaderCell>
            <ListHeaderCell>Photos</ListHeaderCell>
            <ListHeaderCell>Storefront</ListHeaderCell>
            <ListHeaderCell></ListHeaderCell>
          </ListHeader>
          <ListRows :items="product.variants" row-key="name" v-slot="{ item }">
            <ListRow :value="item.name">
              <ListCell>
                <button class="flex min-w-0 items-center gap-2.5" @click.stop="openVariant(item)">
                  <Thumb :image="item.images[0]" size="size-7" />
                  <span class="truncate text-base text-ink-gray-8">{{ item.option }}</span>
                </button>
              </ListCell>
              <ListCell>
                <span class="truncate text-base text-ink-gray-5">
                  {{ item.sizes.map((s) => s.size).join(', ') || '—' }}
                </span>
              </ListCell>
              <ListCell>
                <!-- One price for the whole row: sets every size under this variant
                     in one pass (catalog.set_variant_price), the same bulk operation
                     create_product uses. Per-size prices are edited on the variant's
                     own page, where there is room to show them individually. What is
                     shown and written is the rate a shopper is charged — see
                     shownPrice in data/product.js — not the compare-at above it. -->
                <EditableValue
                  :model-value="shownPrice(item.sizes[0])"
                  label="Price"
                  format="money"
                  @update:model-value="(rate) => setPrice(item, rate)"
                />
              </ListCell>
              <ListCell>
                <!-- Read-only: commera only exposes receiving stock (additive), not
                     setting on-hand to an arbitrary number — see VariantDetail. -->
                <EditableValue
                  :model-value="item.sizes.reduce((sum, s) => sum + (s.stock ?? 0), 0)"
                  label="On hand"
                  readonly
                  :class="stockTone(item.sizes.reduce((sum, s) => sum + (s.stock ?? 0), 0))"
                />
              </ListCell>
              <ListCell>
                <!-- Photos are per variant, so the count is a way in, not a stat. -->
                <button
                  class="flex items-center gap-1.5 rounded-4 px-1.5 py-0.5 hover:bg-surface-gray-2"
                  @click.stop="openVariant(item)"
                >
                  <span
                    class="size-3.5"
                    :class="item.images.length ? 'lucide-image text-ink-gray-6' : 'lucide-image-plus text-ink-gray-4'"
                    aria-hidden="true"
                  />
                  <span class="text-base tabular-nums" :class="item.images.length ? 'text-ink-gray-7' : 'text-ink-gray-4'">
                    {{ item.images.length || 'Add' }}
                  </span>
                </button>
              </ListCell>
              <ListCell>
                <!-- Why it cannot go live matters more than that it has not, so a blocked
                     option names what it is missing instead of just reading "Hidden". -->
                <Badge
                  v-if="item.is_published"
                  label="Live"
                  theme="green"
                  variant="subtle"
                />
                <Badge
                  v-else-if="publishBlockers(item).length"
                  :label="publishBlockers(item).join(', ')"
                  theme="amber"
                  variant="subtle"
                />
                <Badge v-else label="Hidden" theme="gray" variant="subtle" />
              </ListCell>
              <ListCell>
                <Dropdown :options="rowActions(item)" @click.stop>
                  <Button icon="lucide-ellipsis" label="Options for this variant" variant="ghost" />
                </Dropdown>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <EmptyState
        v-if="!product.variants.length"
        compact
        icon="lucide-layers"
        title="No variants yet"
        description="Variants are the buyable combinations — a colour in a size."
      />
    </div>
  </section>

  <VariantDialog v-model:open="showVariant" :variant="editing" :product="product" @saved="emit('saved')" />
</template>

