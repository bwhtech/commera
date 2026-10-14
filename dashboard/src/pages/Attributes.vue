<script setup>
import { computed, ref } from 'vue'
import { Button, ScrollArea, Skeleton, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAdminRead, useAdminAction } from '../data/api'

const attributesRequest = useAdminRead('catalog.get_attributes')
const attributes = computed(() => attributesRequest.data ?? [])

const createAction = useAdminAction('catalog.create_attribute')

function addAttribute() {
  dialog.prompt({
    title: 'New attribute',
    message: 'Attributes are shared across products. Any product can turn one into a variant option.',
    fields: [
      { name: 'name', label: 'Name', required: true },
      { name: 'values', label: 'Values', description: 'Comma separated' },
    ],
    onConfirm: async ({ values }) => {
      try {
        await createAction.submit({ name: values.name, values: values.values })
      } catch {
        // A failure already toasted inside useAdminAction — this is also where the abbreviation
        // guard would fire if it ever could here (see catalog.check_abbreviations_are_distinct);
        // it can't in practice, because create_attribute auto-generates every abbreviation fresh.
        return
      }
      toast.success(`"${values.name}" created`)
      attributesRequest.reload()
    },
  })
}

const openAttribute = ref(null)
const valuesDialogOpen = ref(false)

function editAttribute(attribute) {
  openAttribute.value = attribute
  valuesDialogOpen.value = true
}
</script>

<template>
  <AppPageHeader title="Attributes">
    <template #actions>
      <Button label="New attribute" icon-left="lucide-plus" variant="solid" theme="gray" @click="addAttribute" />
    </template>
  </AppPageHeader>

  <PageBody width="narrow">
    <div
      v-if="attributesRequest.loading"
      class="divide-y divide-outline-gray-1 border-y border-outline-gray-1"
    >
      <div v-for="row in 4" :key="row" class="flex items-start gap-4 py-4">
        <div class="min-w-0 flex-1">
          <Skeleton class="h-4 w-32 rounded-4" />
          <Skeleton class="mt-2 h-3.5 w-40 rounded-4" />
          <div class="mt-2 flex flex-wrap gap-1.5">
            <Skeleton class="h-5 w-12 rounded-4" />
            <Skeleton class="h-5 w-16 rounded-4" />
            <Skeleton class="h-5 w-10 rounded-4" />
          </div>
        </div>
      </div>
    </div>

    <!-- The list scrolls on its own, so the page header stays put while you
         work down a long set of attributes. -->
    <ScrollArea v-scroll-fade
      v-else-if="attributes.length"
      class="max-h-[calc(100vh-15rem)] border-y border-outline-gray-1"
    >
      <div class="divide-y divide-outline-gray-1">
        <div
          v-for="attribute in attributes"
          :key="attribute.name"
          class="flex cursor-pointer items-start gap-4 px-2 py-4 hover:bg-surface-gray-2"
          role="button"
          tabindex="0"
          :aria-label="`Edit ${attribute.name}`"
          @click="editAttribute(attribute)"
          @keyup.enter="editAttribute(attribute)"
        >
          <div class="min-w-0 flex-1">
            <p class="text-base text-ink-gray-8">{{ attribute.name }}</p>
            <p class="mt-1 text-sm text-ink-gray-5">Used by {{ attribute.used_by }} products</p>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="value in attribute.values"
                :key="value.value"
                class="flex items-center gap-1.5 rounded-1 bg-surface-gray-2 px-1.5 py-0.5 text-sm text-ink-gray-7"
              >
                <SwatchDot
                  v-if="value.color || value.image"
                  :color="value.color"
                  :image="value.image"
                  :label="value.value"
                  size="xs"
                />
                {{ value.value }}
              </span>
            </div>
          </div>
          <Button label="Edit" variant="ghost" @click.stop="editAttribute(attribute)" />
        </div>
      </div>
    </ScrollArea>

    <EmptyState
      v-else
      icon="lucide-tags"
      title="No attributes yet"
      description="Attributes are the choices a shopper picks — size, colour, format."
    >
      <Button label="New attribute" icon-left="lucide-plus" variant="solid" theme="gray" @click="addAttribute" />
    </EmptyState>
  </PageBody>

  <AttributeValuesDialog
    v-model:open="valuesDialogOpen"
    :attribute="openAttribute"
    @saved="attributesRequest.reload()"
  />
</template>
