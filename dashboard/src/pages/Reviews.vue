<script setup>
import { computed, ref, watch } from 'vue'
import { Avatar, Rating, Switch, TabButtons, TextInput, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ListPagination from '../components/ListPagination.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAdminAction, useAdminRead } from '../data/api'
import { errorMessage } from '../data/errors'
import { shortDate } from '../data/format'
import { useIsMobile } from '../utils/useIsMobile'
import { ia } from '../ia/store'

const TABS = [
  { label: 'Unpublished', value: 'unpublished' },
  { label: 'Published', value: 'published' },
]

// Approve-first: a new review lands unpublished, so that is the merchant's
// normal working queue, not a low-activity fallback tab.
const tab = ref('unpublished')
const query = ref('')
const page = ref(1)
const pageSize = ref(20)

const reviewsRequest = useAdminRead('reviews.get_reviews', {
  params: () => ({
    tab: tab.value,
    search: query.value || undefined,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

// A tab or search change moves what page one is, so it sends you back to it.
watch([tab, query], () => (page.value = 1))

const total = computed(() => reviewsRequest.data?.total ?? 0)
const rows = computed(() => reviewsRequest.data?.reviews ?? [])

// "Try a different search term" is a lie on the Unpublished tab of a store
// with no reviews at all yet — the state this list is most often first seen in.
const isFiltered = computed(() => Boolean(query.value))

const isMobile = useIsMobile()

// Below `sm` the List overrides itself to two tracks and the middle cells hide, so a
// five-cell skeleton row would spill into an implicit second grid row and draw at
// double height. Recheck this if the max-sm column override or any cell changes.
const skeletonColumns = computed(() => (isMobile.value ? 2 : 5))

const publishAction = useAdminAction('reviews.set_published', { quiet: true })

// Optimistic so the switch never snaps back to its old state mid-drag; a
// refusal restores it and toasts why. `@click.stop` on the Switch (in the
// template) is what stops this from also navigating into the review's own row.
async function togglePublished(row) {
  const nextValue = !row.is_published
  row.is_published = nextValue
  await publishAction.submit({ name: row.name, published: nextValue })
  if (publishAction.error) {
    row.is_published = !nextValue
    toast.error(errorMessage(publishAction.error))
  }
}
</script>

<template>
  <AppPageHeader title="Reviews" />

  <PageBody>
    <div class="flex flex-wrap items-center gap-2">
      <TabButtons v-model="tab" size="sm" :options="TABS" />
      <TextInput
        v-model="query"
        class="ml-auto w-56"
        placeholder="Search reviews"
        icon-left="lucide-search"
      />
    </div>

    <div class="mt-3 overflow-x-auto">
      <!-- 44rem is the width the five columns need; a phone gets two of them instead, because
           a scroll the reader cannot see reads as a rendering fault rather than as more table.
           Do not lower the `min-w` — below the columns' own sum the 1fr track collapses to
           zero and the review cell disappears. -->
      <List
        class="sm:min-w-[44rem]"
        :row-height="Math.max(ia.density, 48)"
        :columns="{ base: ['minmax(0,1fr)', 'auto'], sm: ['1fr', '9rem', '9rem', '7rem', '5rem'] }"
      >
        <ListHeader>
          <ListHeaderCell>Review</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Product</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Shopper</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Submitted</ListHeaderCell>
          <ListHeaderCell>Published</ListHeaderCell>
        </ListHeader>

        <!-- `loading` flips on every param change and the request keeps the previous
             `data`, so guarding on it alone would blank a loaded table on each keystroke
             or tab switch. The skeleton means first load only. -->
        <ListSkeleton v-if="reviewsRequest.loading && !rows.length" :columns="skeletonColumns" />

        <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
          <ListRow :route="`/reviews/${item.name}`" :value="item.name">
            <ListCell>
              <div class="flex min-w-0 items-center gap-2.5">
                <Rating :model-value="item.rating" disabled size="sm" />
                <div class="min-w-0">
                  <p class="truncate text-base text-ink-gray-8">{{ item.review_title || 'Untitled review' }}</p>
                  <p class="truncate text-sm text-ink-gray-5">{{ item.comment }}</p>
                </div>
              </div>
            </ListCell>
            <ListCell class="max-sm:hidden">
              <span class="truncate text-base text-ink-gray-7">{{ item.product?.name ?? '—' }}</span>
            </ListCell>
            <ListCell class="max-sm:hidden">
              <div class="flex min-w-0 items-center gap-2">
                <Avatar :label="item.shopper" size="sm" />
                <span class="truncate text-base text-ink-gray-7">{{ item.shopper }}</span>
              </div>
            </ListCell>
            <ListCell class="max-sm:hidden">
              <span class="text-sm text-ink-gray-5">{{ shortDate(item.creation) }}</span>
            </ListCell>
            <ListCell>
              <Switch :model-value="item.is_published" @click.stop @update:model-value="togglePublished(item)" />
            </ListCell>
          </ListRow>
        </ListRows>
      </List>
    </div>

    <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />

    <EmptyState
      v-if="!reviewsRequest.loading && !rows.length"
      icon="lucide-star"
      :title="tab === 'unpublished' ? 'No reviews waiting on you' : 'No published reviews yet'"
      :description="
        tab === 'unpublished'
          ? 'New reviews land here for you to approve before they reach the storefront.'
          : 'Publish a review from the Unpublished tab to see it here.'
      "
      :filtered="isFiltered"
      filtered-title="No reviews match that search"
      filtered-description="Try a different search term."
    />
  </PageBody>
</template>
