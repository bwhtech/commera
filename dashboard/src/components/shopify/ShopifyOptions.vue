<script setup>
import { reactive, watch } from 'vue'
import { FormControl, Switch } from 'frappe-ui'
import { saveOption, shopify } from '../../data/shopifyImport'

const SWITCHES = [
  { fieldname: 'publish_active_products', label: 'Publish active products', hint: 'Pages without images stay unpublished.' },
  { fieldname: 'import_inventory', label: 'Import stock', hint: 'Sets each size to its Shopify quantity in the Ecommerce Warehouse.' },
  { fieldname: 'add_collections_to_menu', label: 'Add collections to the store menu', hint: 'Off: collections are created but stay out of the menu.' },
]

// What is being typed, separate from what the server holds, so a refused save can roll back.
const draft = reactive({})
watch(
  () => shopify.overview?.options,
  (options) => Object.assign(draft, options ?? {}),
  { immediate: true },
)

// One field per save, when it settles — the same rule the Settings panels follow.
async function commit(fieldname, value) {
  if (shopify.overview.options[fieldname] === value) return
  const saved = await saveOption(fieldname, value)
  if (!saved) draft[fieldname] = shopify.overview.options[fieldname]
}
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-5">
    <h2 class="text-lg-semibold text-ink-gray-9">How products are mapped</h2>
    <p class="mt-1 text-p-sm text-ink-gray-6">
      Commera gives each colour its own product page and puts every other option in the size picker.
      A product with a third option gets joined size labels, for example M / Cotton.
    </p>

    <div class="mt-5 grid gap-4 sm:grid-cols-2">
      <FormControl
        v-model="draft.page_option_names"
        type="textarea"
        label="Options that make product pages"
        description="One Shopify option name per line."
        @blur="commit('page_option_names', draft.page_option_names)"
      />
      <div class="space-y-4">
        <FormControl
          v-model="draft.option_attribute"
          label="Commera attribute for those values"
          placeholder="Color"
          @blur="commit('option_attribute', draft.option_attribute)"
        />
        <FormControl
          v-model="draft.default_collection"
          label="Collection for products in no collection"
          placeholder="Shopify"
          @blur="commit('default_collection', draft.default_collection || null)"
        />
      </div>
    </div>

    <div class="mt-5 divide-y divide-outline-gray-1 border-t border-outline-gray-1">
      <div v-for="row in SWITCHES" :key="row.fieldname" class="flex items-center gap-4 py-3">
        <div class="min-w-0 flex-1">
          <div class="text-base text-ink-gray-8">{{ row.label }}</div>
          <div class="text-p-sm text-ink-gray-5">{{ row.hint }}</div>
        </div>
        <Switch
          :model-value="Boolean(draft[row.fieldname])"
          @update:model-value="(value) => { draft[row.fieldname] = value ? 1 : 0; commit(row.fieldname, value ? 1 : 0) }"
        />
      </div>
    </div>
  </section>
</template>
