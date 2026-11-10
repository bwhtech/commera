<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, Combobox, FormControl, MultiSelect, Switch, toast } from 'frappe-ui'
import { useNavMenu } from '../../data/navMenu'
import { useLinkSearch } from '../../data/linkSearch'
import { __ } from '../../data/translation'

const { selected, mutate } = useNavMenu()

const emit = defineEmits(['remove'])

const LINK_TYPES = [
  { label: __('Nothing — heading only'), value: '' },
  { label: __('Item groups'), value: 'Item Group' },
  { label: __('Brand'), value: 'Brand' },
  { label: __('Custom URL'), value: 'URL' },
]

const form = reactive({
  label: '',
  route_slug: '',
  link_type: '',
  item_groups: [],
  brand: '',
  url: '',
  icon: '',
  meta_title: '',
  meta_description: '',
  noindex: false,
})

const saving = ref(false)

const isRoot = computed(() => Boolean(selected.value && !selected.value.parent))

watch(
  () => selected.value?.name,
  () => {
    const node = selected.value
    if (!node) return
    form.label = node.label
    form.route_slug = node.route_slug
    form.link_type = node.link_type
    form.item_groups = [...node.item_groups]
    form.brand = node.brand
    form.url = node.url
    form.icon = node.icon
    form.meta_title = node.meta_title
    form.meta_description = node.meta_description
    form.noindex = Boolean(node.noindex)
  },
  { immediate: true },
)

const itemGroupSearch = useLinkSearch('navigation.get_link_options', () => ({ doctype: 'Item Group' }))
const brandSearch = useLinkSearch(
  'navigation.get_link_options',
  () => ({ doctype: 'Brand' }),
  () => form.brand,
)

// A search returns only what matches the query, so linked values are merged in or a
// saved group vanishes as soon as someone types.
function withSelected(options, chosen) {
  const merged = new Map(options.map((option) => [option.value, option]))
  for (const value of chosen) {
    if (value && !merged.has(value)) merged.set(value, { label: value, value })
  }
  return [...merged.values()]
}

const itemGroupOptions = computed(() =>
  withSelected(itemGroupSearch.results.data ?? [], form.item_groups),
)

const brandOptions = computed(() => withSelected(brandSearch.results.data ?? [], [form.brand]))

function linkTarget() {
  if (form.link_type === 'Item Group') return form.item_groups
  if (form.link_type === 'Brand') return form.brand
  if (form.link_type === 'URL') return form.url
  return null
}

async function save() {
  const node = selected.value
  if (!node) return

  saving.value = true
  try {
    const saved = await mutate('update_node', {
      name: node.name,
      display_name: form.label,
      link_type: form.link_type,
      link_target: linkTarget(),
      // The server rejects a blank slug outright, so an untouched optional slug is
      // left out of the payload.
      route_slug: form.route_slug || undefined,
      icon: form.icon,
      meta_title: form.meta_title,
      meta_description: form.meta_description,
      noindex: form.noindex ? 1 : 0,
    })
    if (saved) toast.success(__('Menu entry saved'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="!selected" class="grid h-full place-items-center px-5 py-10 text-center">
    <div>
      <p class="text-base text-ink-gray-6">{{ __('Pick an entry to edit it') }}</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        {{ __('Drag entries to reorder them, or drop one onto another to nest it.') }}
      </p>
    </div>
  </div>

  <div v-else class="flex h-full flex-col">
    <div class="flex min-h-12 items-center justify-between border-b border-outline-gray-1 px-5">
      <span class="truncate text-base font-medium text-ink-gray-8">{{ selected.label }}</span>
      <Button
        variant="ghost"
        theme="red"
        icon-left="lucide-trash-2"
        :label="__('Delete')"
        @click="emit('remove', selected)"
      />
    </div>

    <div v-scroll-fade class="min-h-0 flex-1 overflow-y-auto px-5 pb-8 pt-5">
      <div class="space-y-4">
        <FormControl v-model="form.label" :label="__('Menu label')" required />

        <FormControl
          v-model="form.route_slug"
          :label="__('URL slug')"
          :required="isRoot"
          :description="
            isRoot
              ? __('Used in the storefront address for this section.')
              : __('Optional. Top-level sections need one; entries below them do not.')
          "
        />

        <FormControl
          v-model="form.link_type"
          type="select"
          :label="__('Links to')"
          :options="LINK_TYPES"
          :description="__('Leave as a heading to show a label that is not clickable.')"
        />

        <MultiSelect
          v-if="form.link_type === 'Item Group'"
          v-model="form.item_groups"
          v-model:open="itemGroupSearch.open.value"
          v-model:query="itemGroupSearch.query.value"
          :options="itemGroupOptions"
          :filterable="false"
          :loading="itemGroupSearch.results.loading"
          :label="__('Item groups')"
          :description="__('Products from every group listed here appear together under this entry.')"
          :placeholder="__('Search item groups')"
        />

        <Combobox
          v-else-if="form.link_type === 'Brand'"
          v-model="form.brand"
          v-model:open="brandSearch.open.value"
          v-model:query="brandSearch.query.value"
          :options="brandOptions"
          :filterable="false"
          :loading="brandSearch.results.loading"
          :label="__('Brand')"
          :placeholder="__('Search brands')"
        />

        <FormControl
          v-else-if="form.link_type === 'URL'"
          v-model="form.url"
          :label="__('URL')"
          :description="__('Where this entry sends shoppers.')"
        />

        <FormControl v-model="form.icon" :label="__('Icon')" :description="__('Optional icon name or CSS class.')" />
      </div>

      <div class="mt-8 space-y-4">
        <h3 class="text-base font-medium text-ink-gray-8">{{ __('Search engine listing') }}</h3>

        <FormControl
          v-model="form.meta_title"
          :label="__('Page title')"
          :description="__('Defaults to the menu label and your store name.')"
        />
        <FormControl
          v-model="form.meta_description"
          type="textarea"
          :label="__('Description')"
          :description="__('Shown under the title in search results.')"
        />
        <Switch
          v-model="form.noindex"
          :label="__('Hide from search engines')"
          :description="__('Asks crawlers not to list this page.')"
        />
      </div>
    </div>

    <div class="flex justify-end border-t border-outline-gray-1 px-5 py-3">
      <Button variant="solid" theme="gray" :label="__('Save')" :loading="saving" @click="save" />
    </div>
  </div>
</template>
