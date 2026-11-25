<script setup>
import { computed, ref } from 'vue'
import { Button, dialog, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import Thumb from '../components/Thumb.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import BulkBar from '../components/BulkBar.vue'
import EditableValue from '../components/EditableValue.vue'
import { useAdminRead, useAdminAction, trySubmit } from '../data/api'
import { hasPrice, isPriceValid, priceFields, priceRates } from '../data/product'
import { __ } from '../data/translation'
import { ia } from '../ia/store'
import { useBulkAction } from '../utils/useBulkAction'

const selecting = ref(false)
const selection = ref([])

function endSelecting() {
  selecting.value = false
  selection.value = []
}

const pricingRequest = useAdminRead('catalog.get_pricing_rows', {
  params: () => ({ page_length: 500 }),
  refetch: true,
})

const rows = computed(() =>
  (pricingRequest.data?.rows ?? []).map((row) => ({
    ...row,
    ...priceFields(row),
  })),
)

const priceAction = useAdminAction('catalog.set_variant_price')
// Its own request, quiet: a bulk run reports once at the end, and must not abort (or be aborted
// by) a single row's inline edit on the shared one.
const bulkPriceAction = useAdminAction('catalog.set_variant_price', { quiet: true })
const { running: bulkRunning, run: runBulk } = useBulkAction()

function pricingError(fields) {
  if (!hasPrice(fields.discountedPrice)) return __('Enter a discounted price above zero.')
  return isPriceValid(fields) ? '' : __('Price must be higher than the discounted price.')
}

function repriceAll(label, selected, fieldsFor, sentences) {
  const write = (row) => {
    const fields = fieldsFor(row)
    const error = pricingError(fields)
    if (error) return Promise.reject(new Error(error))
    return bulkPriceAction.submit({ style_attribute_variant: row.name, ...priceRates(fields) })
  }
  return runBulk(label, selected, write, {
    sentences,
    after: ({ failed }) => {
      selection.value = failed.map(({ item }) => item.name)
      if (!failed.length) endSelecting()
      return pricingRequest.reload()
    },
  })
}

// The same variant-wide bulk write (catalog.set_variant_price) the product page's own variant
// matrix uses, applying one rate to every size under the variant.
async function savePrices(row, fields) {
  const error = pricingError(fields)
  if (error) return toast.error(error)
  const saved = await trySubmit(priceAction, { style_attribute_variant: row.name, ...priceRates(fields) })
  if (!saved) return
  toast.success(__('Price updated for {0} ({1} sizes)', [row.title, row.size_count]))
  pricingRequest.reload()
}

function bulkRaisePrice() {
  const ids = [...selection.value]
  const selected = rows.value.filter((row) => ids.includes(row.name))
  if (!selected.length) return

  dialog.prompt({
    title: ids.length === 1 ? __('Raise price on 1 item') : __('Raise price on {0} items', [ids.length]),
    message: __('Raises Price and Discounted price by this percentage, rounded to the nearest paisa.'),
    fields: [{ name: 'value', label: __('Raise by %'), type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const pct = Number(values.value) || 0
      await repriceAll(
        'Raise by %',
        selected,
        (row) => ({ price: row.price && raise(row.price, pct), discountedPrice: raise(row.discountedPrice, pct) }),
        {
          all: (count) => (count === 1 ? __('1 item repriced') : __('{0} items repriced', [count])),
          some: (done, total, failed) => __('{0} of {1} items repriced. {2} failed', [done, total, failed]),
        },
      )
    },
  })
}

function raise(rate, pct) {
  return Math.round(rate * (1 + pct / 100) * 100) / 100
}

function bulkSetDiscountedPrice() {
  const ids = [...selection.value]
  const selected = rows.value.filter((row) => ids.includes(row.name))
  if (!selected.length) return

  dialog.prompt({
    title:
      ids.length === 1
        ? __('Set discounted price on 1 item')
        : __('Set discounted price on {0} items', [ids.length]),
    message: __('Shoppers pay this and see Price crossed out when it is higher.'),
    fields: [{ name: 'value', label: __('Discounted price'), type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const rate = Math.max(0, Number(values.value) || 0)
      await repriceAll('Set discounted price', selected, (row) => ({ price: row.price, discountedPrice: rate }), {
        all: (count) => (count === 1 ? __('1 item repriced') : __('{0} items repriced', [count])),
        some: (done, total, failed) => __('{0} of {1} items repriced. {2} failed', [done, total, failed]),
      })
    },
  })
}
</script>

<template>
  <AppPageHeader
    :title="__('Edit prices')"
    back-to="/products"
    :breadcrumbs="[{ label: __('Products'), route: '/products' }, { label: __('Edit prices') }]"
  />

  <PageBody>
    <div class="flex flex-wrap items-center gap-3">
      <p v-if="!pricingRequest.loading" class="text-sm text-ink-gray-5">
        {{ __('{0} sellable units', [rows.length]) }}
      </p>
      <Button
        class="ms-auto"
        :label="selecting ? __('Cancel selection') : __('Select')"
        icon-left="lucide-list-checks"
        :variant="selecting ? 'solid' : 'subtle'"
        theme="gray"
        @click="selecting ? endSelecting() : (selecting = true)"
      />
    </div>

    <BulkBar
      v-if="selecting"
      :count="selection.length"
      :selected-label="selection.length === 1 ? __('1 item selected') : __('{0} items selected', [selection.length])"
      :empty-label="__('Select items to act on them')"
      :busy="Boolean(bulkRunning)"
      @done="endSelecting"
    >
      <Button :label="__('Raise by %')" :loading="bulkRunning === 'Raise by %'" @click="bulkRaisePrice" />
      <Button
        :label="__('Set discounted price')"
        :loading="bulkRunning === 'Set discounted price'"
        @click="bulkSetDiscountedPrice"
      />
    </BulkBar>

    <div class="mt-3 overflow-x-auto">
      <List
      v-model:selection="selection"
      class="min-w-[50rem]"
      :selectable="selecting"
      :row-height="Math.max(ia.density, 44)"
      :columns="['1fr', '11rem', '7rem', '9rem']"
    >
      <ListHeader>
        <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('SKU') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('Price') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('Discounted price') }}</ListHeaderCell>
      </ListHeader>
      <!-- `loading` flips on every reload and the request keeps the previous `data`,
           so guarding on it alone would blank a loaded table after every price edit.
           The skeleton means first load only. -->
      <ListSkeleton v-if="pricingRequest.loading && !rows.length" :columns="4" />
      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :value="item.name">
          <ListCell>
            <div class="flex min-w-0 items-center gap-2.5">
              <Thumb :image="item.image" size="size-7" />
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ item.title }}</p>
                <p class="truncate text-sm text-ink-gray-5">{{ item.subtitle }}</p>
              </div>
            </div>
          </ListCell>
          <ListCell><span class="truncate text-base text-ink-gray-5">{{ item.sku }}</span></ListCell>
          <ListCell>
            <EditableValue
              :model-value="item.price ?? 0"
              :label="__('Price')"
              :description="__('Enter 0 to remove the crossed-out price.')"
              empty-label="—"
              format="money"
              @update:model-value="(rate) => savePrices(item, { price: rate, discountedPrice: item.discountedPrice })"
            />
          </ListCell>
          <ListCell>
            <EditableValue
              :model-value="item.discountedPrice ?? 0"
              :label="__('Discounted price')"
              format="money"
              @update:model-value="(rate) => savePrices(item, { price: item.price, discountedPrice: rate })"
            />
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <EmptyState v-if="!pricingRequest.loading && !rows.length" icon="lucide-tag" :title="__('No sellable items yet')" :description="__('Add a product to start pricing it.')" />
  </PageBody>
</template>

