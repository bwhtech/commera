<script setup>
import { computed, ref } from 'vue'
import { Button, ScrollArea, Skeleton, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import AttributeValuesDialog from '../components/AttributeValuesDialog.vue'
import SwatchDot from '../components/SwatchDot.vue'
import { useAdminRead, useAdminAction, trySubmit } from '../data/api'
import { __ } from '../data/translation'

const attributesRequest = useAdminRead('catalog.get_attributes')
const attributes = computed(() => attributesRequest.data ?? [])

const createAction = useAdminAction('catalog.create_attribute')

function addAttribute() {
  dialog.prompt({
    title: __('New attribute'),
    message: __('Attributes are shared across products. Any product can turn one into a variant option.'),
    fields: [
      { name: 'name', label: __('Name'), required: true },
      { name: 'values', label: __('Values'), description: __('Comma separated') },
    ],
    onConfirm: async ({ values }) => {
      const created = await trySubmit(createAction, { name: values.name, values: values.values })
      // A failure already toasted inside useAdminAction — this is also where the abbreviation
      // guard would fire if it ever could here (see catalog.check_abbreviations_are_distinct);
      // it can't in practice, because create_attribute auto-generates every abbreviation fresh.
      if (!created) return
      toast.success(__('"{0}" created', [values.name]))
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
  <AppPageHeader :title="__('Attributes')">
    <template #actions>
      <Button :label="__('New attribute')" icon-left="lucide-plus" variant="solid" theme="gray" @click="addAttribute" />
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
      class="max-h-[calc(100dvh-15rem)] border-y border-outline-gray-1"
    >
      <div class="divide-y divide-outline-gray-1">
        <div
          v-for="attribute in attributes"
          :key="attribute.name"
          class="flex cursor-pointer items-start gap-4 px-2 py-4 hover:bg-surface-gray-2"
          role="button"
          tabindex="0"
          :aria-label="__('Edit {0}', [attribute.name])"
          @click="editAttribute(attribute)"
          @keyup.enter="editAttribute(attribute)"
        >
          <div class="min-w-0 flex-1">
            <p class="text-base text-ink-gray-8">{{ attribute.name }}</p>
            <p class="mt-1 text-sm text-ink-gray-5">{{ __('Used by {0} products', [attribute.used_by]) }}</p>
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
          <Button :label="__('Edit')" variant="ghost" @click.stop="editAttribute(attribute)" />
        </div>
      </div>
    </ScrollArea>

    <EmptyState
      v-else
      icon="lucide-tags"
      :title="__('No attributes yet')"
      :description="__('Attributes are the choices a shopper picks — size, colour, format.')"
    >
      <Button :label="__('New attribute')" icon-left="lucide-plus" variant="solid" theme="gray" @click="addAttribute" />
    </EmptyState>
  </PageBody>

  <AttributeValuesDialog
    v-model:open="valuesDialogOpen"
    :attribute="openAttribute"
    @saved="attributesRequest.reload()"
  />
</template>
