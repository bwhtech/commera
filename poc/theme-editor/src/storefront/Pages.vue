<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import StorefrontShell from './StorefrontShell.vue'
import { contentPages, liveTheme, templatesFor } from './data.js'

// Content pages: About us, FAQ, policies. Written as rich text and rendered by
// the live theme's page template, like Shopify's Online Store → Pages.
const router = useRouter()
const theme = computed(liveTheme)
const templateLabel = (value) => templatesFor(theme.value).find((template) => template.value === value)?.label ?? 'Default page'

function addPage() {
  const name = `untitled-${contentPages.length + 1}`
  contentPages.unshift({ name, title: '', visible: false, template: 'page', updated: 'Just now', content: '', content_ar: '' })
  router.push(`/storefront/pages/${name}`)
}
</script>

<template>
  <StorefrontShell>
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Pages</h1>
        <p class="mt-1 text-base text-ink-gray-6">
          Pages like About us, FAQ or your policies. You write them here; your live theme
          (<span class="font-medium text-ink-gray-7">{{ theme.title }}</span>) lays them out.
        </p>
      </div>
      <Button variant="solid" icon-left="lucide-plus" label="Add page" data-add-page @click="addPage" />
    </div>

    <div class="mt-6 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
      <button
        v-for="page in contentPages"
        :key="page.name"
        class="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-surface-gray-1"
        :data-content-page="page.name"
        @click="router.push(`/storefront/pages/${page.name}`)"
      >
        <span class="lucide-file-text size-4 text-ink-gray-6" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-base font-medium text-ink-gray-9">{{ page.title || 'Untitled page' }}</p>
          <p class="text-sm text-ink-gray-5">/{{ page.name }} · {{ templateLabel(page.template) }} · updated {{ page.updated }}</p>
        </div>
        <Badge :label="page.visible ? 'Visible' : 'Hidden'" :theme="page.visible ? 'green' : 'gray'" />
      </button>
    </div>
  </StorefrontShell>
</template>
