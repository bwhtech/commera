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
import { __ } from '../../data/translation'
import { createSequence } from '../../utils/sequence'

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
// The list's own state: 'idle' | 'loading' | 'ready' | 'error'. Confirm waits for `ready`, because the
// blocked-options note it depends on comes from this answer.
const status = ref('idle')
const submitting = ref(false)

const publishing = computed(() => Boolean(props.target?.publish))
const count = computed(() => props.target?.count ?? 0)
const options = computed(() => cascade.value?.products ?? [])
const matching = computed(() => cascade.value?.matching ?? 0)
const incomplete = computed(() => cascade.value?.incomplete ?? 0)

const title = computed(() =>
  publishing.value
    ? __('Publish the options under "{0}"?', [props.target?.label])
    : __('Take the options under "{0}" off the storefront?', [props.target?.label]),
)

const summary = computed(() => {
  if (publishing.value) {
    return count.value
      ? count.value === 1
        ? __('1 option will go live on your storefront.')
        : __('{0} options will go live on your storefront.', [count.value])
      : __('None of these options can go live yet.')
  }
  return count.value
    ? count.value === 1
      ? __('1 option will come off your storefront. It stays in your catalogue.')
      : __('{0} options will come off your storefront. They stay in your catalogue.', [count.value])
    : __('None of these options are on your storefront right now.')
})

// Only publishing can be blocked, and only a merchant who is told before confirming can fix it.
const blockedNote = computed(() => {
  if (!publishing.value || !incomplete.value) return ''
  return incomplete.value === 1
    ? __('1 option is missing images or sizes, so it cannot go live yet and is left as it is.')
    : __('{0} options are missing images or sizes, so they cannot go live yet and are left as they are.', [incomplete.value])
})

const confirmLabel = computed(() => {
  if (!count.value) return publishing.value ? __('Nothing to publish') : __('Nothing to take off')
  if (publishing.value) return count.value === 1 ? __('Publish 1 option') : __('Publish {0} options', [count.value])
  return count.value === 1 ? __('Take 1 option off') : __('Take {0} options off', [count.value])
})

function rowState(option) {
  if (!publishing.value) {
    return option.is_published
      ? { label: __('Coming off'), theme: 'amber' }
      : { label: __('Already off'), theme: 'gray' }
  }
  if (option.is_published) return { label: __('Already live'), theme: 'gray' }
  if (option.blocked_reason) return { label: option.blocked_reason, theme: 'amber' }
  return { label: __('Going live'), theme: 'green' }
}

// Opening resets the search and page, which their own watcher sees too, so one open used to send
// two reads that aborted each other. A read for the same list as the one in flight is skipped, and
// only the newest read may land: a reply for a closed dialog or an older search is dropped.
const loads = createSequence()
let inFlight = ''

async function loadOptions() {
  if (!props.target || !open.value) return
  const params = {
    name: props.target.name,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
    search: search.value || undefined,
  }
  const key = JSON.stringify(params)
  if (status.value === 'loading' && key === inFlight) return
  inFlight = key
  const ticket = loads.next()
  status.value = 'loading'
  const answer = await call('get_cascade_products', params)
  if (!loads.isLatest(ticket)) return
  inFlight = ''
  cascade.value = answer
  status.value = answer ? 'ready' : 'error'
}

watch(open, (isOpen) => {
  if (!isOpen) {
    loads.cancel()
    inFlight = ''
    return
  }
  search.value = ''
  page.value = 1
  cascade.value = null
  status.value = 'idle'
  loadOptions()
})

// A new search is a new list, so it starts at page one.
watch(search, () => (page.value = 1))
watch([search, page, pageSize], loadOptions)

async function confirmPublish() {
  if (submitting.value || status.value !== 'ready') return
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
        ? data.count === 1
          ? __('1 option live on your storefront')
          : __('{0} options live on your storefront', [data.count])
        : data.count === 1
          ? __('1 option taken off your storefront')
          : __('{0} options taken off your storefront', [data.count]),
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
            {{
              __(
                'An option is one colour of a product, with a page of its own. The menu entry itself is not touched — this only changes what shoppers can buy.',
              )
            }}
          </p>
        </div>

        <SearchInput
          v-model="search"
          :placeholder="__('Search these options')"
        />

        <LoadingText v-if="status === 'loading' || status === 'idle'" />

        <div v-else-if="status === 'error'" class="flex flex-col items-center gap-2 py-6 text-center">
          <p class="text-base text-ink-gray-5">{{ __('Could not list these options.') }}</p>
          <Button :label="__('Try again')" @click="loadOptions" />
        </div>

        <template v-else>
          <p v-if="!options.length" class="py-6 text-center text-base text-ink-gray-5">
            {{ __('No options under this entry match.') }}
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
        :disabled="!count || status !== 'ready'"
        :loading="submitting"
        @click="confirmPublish"
      />
    </template>
  </Dialog>
</template>
