<script setup>
import { Badge, Button, Switch } from 'frappe-ui'
import { builderUrl } from '../theme/builder.js'
import { openBuilder } from './openBuilder.js'

// Right panel for a Builder page. Its content is edited in Builder; what the
// theme editor still owns is whether the page wears the store's header and
// footer (the proposed builder_page_layouts hook), and the shared header and
// footer themselves.
const props = defineProps({ page: { type: Object, required: true } })
</script>

<template>
  <div class="flex h-full flex-col" data-builder-page-panel>
    <div class="border-b border-outline-gray-2 px-4 py-3">
      <div class="flex items-center gap-2">
        <span class="lucide-blocks size-4 text-ink-teal-4" aria-hidden="true" />
        <h2 class="min-w-0 flex-1 truncate text-lg font-semibold text-ink-gray-9">{{ page.title }}</h2>
        <Badge :label="page.status" :theme="page.status === 'Published' ? 'green' : 'gray'" />
      </div>
      <p class="mt-1 text-sm text-ink-gray-6">Built in Frappe Builder · {{ page.route }}</p>
    </div>

    <div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
      <Button
        variant="solid"
        class="w-full"
        icon-left="lucide-pencil"
        label="Edit in Builder"
        data-edit-in-builder
        @click="openBuilder(builderUrl('page', { name: page.name }), page.title)"
      />

      <Switch
        :model-value="page.layout === 'commera-theme'"
        label="Use the store's header and footer"
        description="Wraps this page in the active theme, so it looks like the rest of your store."
        @update:model-value="(value) => (page.layout = value ? 'commera-theme' : 'none')"
      />

      <div>
        <p class="mb-2 text-sm text-ink-gray-7">Commera components on this page</p>
        <ul class="space-y-1.5">
          <li v-for="component in page.components" :key="component" class="flex items-center gap-2 text-sm text-ink-gray-8">
            <span class="lucide-component size-3.5 text-ink-gray-5" aria-hidden="true" />
            {{ component }}
          </li>
        </ul>
      </div>

      <p class="text-sm text-ink-gray-5">Last edited {{ page.edited }}. Changes made in Builder appear here when you come back to this tab.</p>
    </div>
  </div>
</template>
