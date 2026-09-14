<script setup>
import { computed, ref } from 'vue'
import { Button, dialog, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ListPagination from '../components/ListPagination.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { ia } from '../ia/store'

const page = ref(1)
const pageSize = ref(10)

const collectionsRequest = useAdminRead('catalog.list_collections', {
  params: () => ({
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

const rows = computed(() => collectionsRequest.data?.collections ?? [])
const total = computed(() => collectionsRequest.data?.total ?? 0)

const createAction = useAdminAction('catalog.create_collection')

function addCollection() {
  dialog.prompt({
    title: 'New collection',
    message: 'A collection groups products the storefront can filter and browse by.',
    fields: [{ name: 'title', label: 'Title', required: true }],
    onConfirm: async ({ values }) => {
      await createAction.submit({ title: values.title })
      // A failure already toasted inside useAdminAction.
      if (createAction.error) return
      toast.success(`"${values.title}" created`)
      collectionsRequest.reload()
    },
  })
}
</script>

<template>
  <AppPageHeader title="Collections">
    <template #actions>
      <Button label="Create collection" icon-left="lucide-plus" variant="solid" theme="gray" @click="addCollection" />
    </template>
  </AppPageHeader>

  <PageBody width="wide">
    <div v-if="collectionsRequest.loading || rows.length" class="mt-3 overflow-x-auto">
      <!-- Collection and Products only: commera has no smart-collection rule engine, so
           "Type" read "manual" and "Condition" read "—" on every row — two columns of no
           information, and a caption under the header apologising for them. -->
      <List
        class="min-w-[20rem]"
        :row-height="ia.density"
        :columns="['minmax(9rem,1fr)', '6rem']"
      >
        <ListHeader>
          <ListHeaderCell>Collection</ListHeaderCell>
          <ListHeaderCell>Products</ListHeaderCell>
        </ListHeader>
        <!-- `loading` flips on every param change and the request keeps the previous
             `data`, so guarding on it alone would blank a loaded table on each page
             change. The skeleton means first load only. -->
        <ListSkeleton v-if="collectionsRequest.loading && !rows.length" :columns="2" />
        <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
          <ListRow :value="item.name">
            <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.name }}</span></ListCell>
            <ListCell><span class="text-base text-ink-gray-7 tabular-nums">{{ item.count }}</span></ListCell>
          </ListRow>
        </ListRows>
      </List>
    </div>

    <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />

    <EmptyState
      v-if="!collectionsRequest.loading && !rows.length"
      icon="lucide-layers"
      title="No collections yet"
      description="Create one to start filing products under it."
    />
  </PageBody>
</template>

