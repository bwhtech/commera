<script setup>
import { computed, ref } from 'vue'
import { Button, TextInput } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import { ia } from '../../ia/store'
import EmptyState from '../EmptyState.vue'
import ReceiveStockDialog from './ReceiveStockDialog.vue'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['received'])

const receiveOpen = ref(false)

// One row per size, not per variant — a size (Color Size Item) is commera's
// real stocked unit, each with its own item_code and Bin quantity.
const rows = computed(() =>
  props.product.variants.flatMap((variant) =>
    variant.sizes.map((size) => ({
      id: size.item_code,
      title: `${variant.option} · ${size.size}`,
      sku: size.item_code,
      committed: size.committed,
      onHand: size.stock,
    })),
  ),
)
</script>

<template>
  <section>
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg-semibold text-ink-gray-8">Stock</h2>
        <p class="mt-1 text-p-sm text-ink-gray-5">On hand per variant.</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Receiving is the only stock write commera has, so it is the one offered
             here; the on-hand column stays read-only. -->
        <Button
          label="Receive stock"
          icon-left="lucide-package-plus"
          :disabled="!rows.length"
          @click="receiveOpen = true"
        />
        <Button label="Open in Inventory" variant="ghost" route="/inventory" />
      </div>
    </div>

    <div class="mt-3 overflow-x-auto">
    <List
      class="min-w-[28rem]"
      :row-height="Math.max(ia.density, 44)"
      :columns="['minmax(7rem,1fr)', 'minmax(8rem,1fr)', '6rem', '6rem']"
    >
      <ListHeader>
        <ListHeaderCell>Variant</ListHeaderCell>
        <ListHeaderCell>SKU</ListHeaderCell>
        <ListHeaderCell>Committed</ListHeaderCell>
        <ListHeaderCell>On hand</ListHeaderCell>
      </ListHeader>
      <ListRows :items="rows" row-key="id" v-slot="{ item }">
        <ListRow :value="item.id">
          <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.title }}</span></ListCell>
          <ListCell><span class="truncate text-base text-ink-gray-5">{{ item.sku }}</span></ListCell>
          <ListCell><span class="text-base text-ink-gray-5 tabular-nums">{{ item.committed }}</span></ListCell>
          <ListCell>
            <!-- Read-only (:model-value only, no write): commera only exposes receiving stock
                 (Style Attribute Variant.receive_stock, additive), not setting on-hand to an
                 arbitrary number — the Receive stock dialog above is the write. -->
            <TextInput :model-value="String(item.onHand)" size="sm" class="w-16" disabled />
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <EmptyState
      v-if="!rows.length"
      compact
      icon="lucide-boxes"
      title="No stock to track yet"
      description="Stock appears once this product has variants."
    />

    <ReceiveStockDialog v-model:open="receiveOpen" :rows="rows" @received="emit('received')" />
  </section>
</template>
