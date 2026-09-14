<script setup>
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import ListPagination from '../../components/ListPagination.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import EmptyState from '../../components/EmptyState.vue'
import ListSkeleton from '../../components/ListSkeleton.vue'
import { usePages } from '../../data/pages'
import { errorMessage } from '../../data/errors'
import { shortDate } from '../../data/format'
import { useIsMobile } from '../../utils/useIsMobile'
import { ia } from '../../ia/store'

const { pages, total, loadError, loading, load } = usePages()

onMounted(load)

const page = ref(1)
const pageSize = ref(10)

// get_pages answers with the whole list, so the paging stays client-side.
const rows = computed(() =>
  pages.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value),
)

const isMobile = useIsMobile()

// Below `sm` the List overrides itself to two tracks and the real rows hide their
// Path and Status cells, so a four-cell skeleton row would spill into an implicit
// second grid row and draw at double height. Recheck this if the max-sm column
// override or either `max-sm:hidden` cell below changes.
const skeletonColumns = computed(() => (isMobile.value ? 2 : 4))

function detailRoute(name) {
  return `/storefront/pages/${encodeURIComponent(name)}`
}
</script>

<template>
  <AppPageHeader title="Pages">
    <template #actions>
      <Button
        label="Add page"
        icon-left="lucide-plus"
        variant="solid"
        theme="gray"
        route="/storefront/pages/new"
      />
    </template>
  </AppPageHeader>

  <PageBody width="wide">
    <p class="text-p-sm text-ink-gray-5">
      Standalone pages — About us, shipping, returns — that your footer and menus can link to.
    </p>

    <EmptyState
      v-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load your pages"
      :description="errorMessage(loadError)"
    />

    <EmptyState
      v-else-if="!loading && !pages.length"
      icon="lucide-file-text"
      title="No pages yet"
      description="Add one to tell shoppers about your store, your shipping or your returns."
    >
      <Button variant="subtle" theme="gray" label="Add page" route="/storefront/pages/new" />
    </EmptyState>

    <template v-else>
      <div class="mt-3 overflow-x-auto">
        <List
          class="max-sm:[--list-columns:minmax(0,1fr)_auto] sm:min-w-[38rem]"
          :row-height="Math.max(ia.density, 44)"
          :columns="['minmax(9rem,1fr)', 'minmax(11rem,1fr)', '7rem', '6rem']"
        >
          <ListHeader class="max-sm:hidden">
            <ListHeaderCell>Page</ListHeaderCell>
            <ListHeaderCell>Path</ListHeaderCell>
            <ListHeaderCell>Status</ListHeaderCell>
            <ListHeaderCell>Updated</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="loading && !pages.length" :columns="skeletonColumns" />
          <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
            <ListRow :to="detailRoute(item.name)" :value="item.name">
              <ListCell>
                <span class="truncate text-base text-ink-gray-8">{{ item.name }}</span>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <span class="truncate text-base text-ink-gray-5">{{ item.url }}</span>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <StatusBadge :status="item.published ? 'published' : 'draft'" />
              </ListCell>
              <ListCell>
                <span class="text-base text-ink-gray-5">{{ shortDate(item.modified) }}</span>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />
    </template>
  </PageBody>
</template>
