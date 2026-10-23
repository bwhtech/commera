<script setup>
/**
 * Publishing what sits under a menu entry is a different object from showing or hiding the entry
 * itself, and the difference is invisible from a dropdown label alone — so the confirm step lists
 * what is about to change, and names what cannot.
 *
 * The server counts Style Attribute Variants, which this dashboard calls options: one colour of a
 * product, with a storefront page of its own. Five products in three colours are fifteen options,
 * so every number here is worded as options rather than products.
 */
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dialog, LoadingText, toast } from 'frappe-ui'
import ListPagination from '../ListPagination.vue'
import SearchInput from '../SearchInput.vue'
import { useNavMenu } from '../../data/navMenu'

const props = defineProps({
  // { name, label, publish, count } — the answer from navigation.get_publish_preview.
  target: { type: Object, default: null },
})

const open = defineModel('open', { type: Boolean, required: true })

const { call, mutate } = useNavMenu()

const search = ref('')
const page = ref(1)
const pageSize = ref(10)
const cascade = ref(null)
const loading = ref(false)
const submitting = ref(false)

const publishing = computed(() => Boolean(props.target?.publish))
const count = computed(() => props.target?.count ?? 0)
const options = computed(() => cascade.value?.products ?? [])
const matching = computed(() => cascade.value?.matching ?? 0)
const incomplete = computed(() => cascade.value?.incomplete ?? 0)

function optionWord(total) {
  return `${total} option${total === 1 ? '' : 's'}`
}

const title = computed(() =>
  publishing.value
    ? `Publish the options under "${props.target?.label}"?`
    : `Take the options under "${props.target?.label}" off the storefront?`,
)

const summary = computed(() => {
  if (publishing.value) {
    return count.value
      ? `${optionWord(count.value)} will go live on your storefront.`
      : 'None of these options can go live yet.'
  }
  return count.value
    ? `${optionWord(count.value)} will come off your storefront. They stay in your catalogue.`
    : 'None of these options are on your storefront right now.'
})

// Only publishing can be blocked, and only a merchant who is told before confirming can fix it.
const blockedNote = computed(() =>
  publishing.value && incomplete.value
    ? `${optionWord(incomplete.value)} are missing images or sizes, so they cannot go live yet and are left as they are.`
    : '',
)

const confirmLabel = computed(() => {
  if (!count.value) return publishing.value ? 'Nothing to publish' : 'Nothing to take off'
  return publishing.value ? `Publish ${optionWord(count.value)}` : `Take ${optionWord(count.value)} off`
})

function rowState(option) {
  if (!publishing.value) {
    return option.is_published
      ? { label: 'Coming off', theme: 'amber' }
      : { label: 'Already off', theme: 'gray' }
  }
  if (option.is_published) return { label: 'Already live', theme: 'gray' }
  if (option.blocked_reason) return { label: option.blocked_reason, theme: 'amber' }
  return { label: 'Going live', theme: 'green' }
}

async function loadOptions() {
  if (!props.target) return

  loading.value = true
  try {
    cascade.value = await call('get_cascade_products', {
      name: props.target.name,
      start: (page.value - 1) * pageSize.value,
      page_length: pageSize.value,
      search: search.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

watch(open, (isOpen) => {
  if (!isOpen) return
  search.value = ''
  page.value = 1
  cascade.value = null
  loadOptions()
})

// A new search is a new list, so it starts at page one.
watch(search, () => (page.value = 1))
watch([search, page, pageSize], loadOptions)

async function confirmPublish() {
  submitting.value = true
  try {
    const data = await mutate('set_published', {
      name: props.target.name,
      publish: props.target.publish,
    })
    if (!data) return

    open.value = false
    toast.success(
      publishing.value
        ? `${optionWord(data.count)} live on your storefront`
        : `${optionWord(data.count)} taken off your storefront`,
    )
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="title" size="2xl">
    <template #default>
      <div class="space-y-4">
        <div class="space-y-1">
          <p class="text-p-base text-ink-gray-7">{{ summary }}</p>
          <p v-if="blockedNote" class="text-p-base text-ink-amber-7">{{ blockedNote }}</p>
          <p class="text-p-base text-ink-gray-5">
            An option is one colour of a product, with a page of its own. The menu entry itself is
            not touched — this only changes what shoppers can buy.
          </p>
        </div>

        <SearchInput
          v-model="search"
          placeholder="Search these options"
        />

        <LoadingText v-if="loading" />

        <template v-else>
          <p v-if="!options.length" class="py-6 text-center text-base text-ink-gray-5">
            No options under this entry match.
          </p>

          <ul v-else class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
            <li
              v-for="option in options"
              :key="option.name"
              class="flex items-center gap-3 px-3 py-2"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-base text-ink-gray-8">{{ option.display_name }}</p>
                <p class="truncate text-sm text-ink-gray-5">{{ option.item_group }}</p>
              </div>
              <Badge v-bind="rowState(option)" class="shrink-0" />
            </li>
          </ul>

          <ListPagination
            v-if="matching"
            v-model:page="page"
            v-model:page-size="pageSize"
            :total="matching"
          />
        </template>
      </div>
    </template>

    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        theme="gray"
        :label="confirmLabel"
        :disabled="!count"
        :loading="submitting"
        @click="confirmPublish"
      />
    </template>
  </Dialog>
</template>
