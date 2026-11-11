<script setup>
import { computed, ref } from 'vue'
import { Button, Select, dialog, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import Thumb from '../components/Thumb.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import BulkBar from '../components/BulkBar.vue'
import EditableValue from '../components/EditableValue.vue'
import { useAdminRead, useAdminAction, trySubmit } from '../data/api'
import { money } from '../data/format'
import { compareAtPrice, pricePayload, shownPrice } from '../data/product'
import { __ } from '../data/translation'
import { ia } from '../ia/store'
import { useBulkAction } from '../utils/useBulkAction'

const selecting = ref(false)
const selection = ref([])

function endSelecting() {
  selecting.value = false
  selection.value = []
}

// commera has no product-type schema at all (confirmed against the doctypes — the same
// gap flagged as open question #1 in docs/commera-open-questions.md, where section 1 substituted
// Collection for Type on its own judgement). That substitution needs the owner's yes/no before it
// is repeated, so this stays a single always-selected option rather than silently becoming
// something it isn't.
const type = ref('all')
const typeOptions = [{ label: __('All types'), value: 'all' }]

const pricingRequest = useAdminRead('catalog.get_pricing_rows', {
  params: () => ({ page_length: 500 }),
  refetch: true,
})

const rows = computed(() =>
  (pricingRequest.data?.rows ?? []).map((row) => ({
    ...row,
    price: shownPrice(row),
    compareAt: compareAtPrice(row),
  })),
)

const priceAction = useAdminAction('catalog.set_variant_price')
// Its own request, quiet: a bulk run reports once at the end, and must not abort (or be aborted
// by) a single row's inline edit on the shared one.
const bulkPriceAction = useAdminAction('catalog.set_variant_price', { quiet: true })
const { running: bulkRunning, run: runBulk } = useBulkAction()

function repriceAll(label, selected, payloadFor, sentences) {
  return runBulk(label, selected, (row) => bulkPriceAction.submit({ style_attribute_variant: row.name, ...payloadFor(row) }), {
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
async function setPrice(row, rate) {
  const saved = await trySubmit(priceAction, { style_attribute_variant: row.name, ...pricePayload(row, rate) })
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
    message: __('Raises the price a shopper actually pays by this percentage, rounded to the nearest paisa.'),
    fields: [{ name: 'value', label: __('Raise by %'), type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const pct = Number(values.value) || 0
      await repriceAll(
        'Raise by %',
        selected,
        (row) => pricePayload(row, Math.round(row.price * (1 + pct / 100) * 100) / 100),
        {
          all: (count) => (count === 1 ? __('1 item repriced') : __('{0} items repriced', [count])),
          some: (done, total, failed) => __('{0} of {1} items repriced. {2} failed', [done, total, failed]),
        },
      )
    },
  })
}

function bulkSetCompareAt() {
  const ids = [...selection.value]
  const selected = rows.value.filter((row) => ids.includes(row.name))
  if (!selected.length) return

  dialog.prompt({
    title: ids.length === 1 ? __('Set compare-at on 1 item') : __('Set compare-at on {0} items', [ids.length]),
    message: __('Sets the struck-through reference price shown above the real price.'),
    fields: [{ name: 'value', label: __('Compare at'), type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const rate = Math.max(0, Number(values.value) || 0)
      await repriceAll('Set compare-at', selected, () => ({ default_rate: rate }), {
        all: (count) =>
          count === 1 ? __('1 item given a compare-at price') : __('{0} items given a compare-at price', [count]),
        some: (done, total, failed) =>
          __('{0} of {1} items given a compare-at price. {2} failed', [done, total, failed]),
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
      <Select v-model="type" :options="typeOptions" disabled />
      <p v-if="!pricingRequest.loading" class="text-sm text-ink-gray-5">
        {{ __('{0} sellable units · one row per variant, priced individually on its product', [rows.length]) }}
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
      <Button :label="__('Set compare-at')" :loading="bulkRunning === 'Set compare-at'" @click="bulkSetCompareAt" />
    </BulkBar>

    <div class="mt-3 overflow-x-auto">
      <List
      v-model:selection="selection"
      class="min-w-[50rem]"
      :selectable="selecting"
      :row-height="Math.max(ia.density, 44)"
      :columns="['1fr', '11rem', '7rem', '8rem']"
    >
      <ListHeader>
        <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('SKU') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('Price') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('Compare at') }}</ListHeaderCell>
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
              :model-value="item.price"
              :label="__('Price')"
              format="money"
              @update:model-value="(rate) => setPrice(item, rate)"
            />
          </ListCell>
          <ListCell>
            <span class="text-base tabular-nums" :class="item.compareAt ? 'text-ink-gray-7' : 'text-ink-gray-4'">
              {{ item.compareAt ? money(item.compareAt) : '—' }}
            </span>
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <EmptyState v-if="!pricingRequest.loading && !rows.length" icon="lucide-tag" :title="__('No sellable items yet')" :description="__('Add a product to start pricing it.')" />
  </PageBody>
</template>

