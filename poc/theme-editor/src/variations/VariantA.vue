<script setup>
import { ref } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardFrame from './DashboardFrame.vue'
import PageRow from './PageRow.vue'
import NewPage from './NewPage.vue'
import { STORE_PAGES, pages } from './data.js'

// Variation A: one screen, one tool. Theme = your store's built-in pages,
// arranged in the theme editor. Pages = extra pages you add, designed in
// Builder. Nothing appears in both places.
const router = useRouter()
const screen = ref('theme')
const newPage = ref(false)
</script>

<template>
  <DashboardFrame
    variant="A"
    :active="screen"
    :items="[{ key: 'theme', label: 'Theme', icon: 'lucide-palette' }, { key: 'pages', label: 'Pages', icon: 'lucide-files' }]"
    @navigate="(key) => (screen = key)"
  >
    <template v-if="screen === 'theme'">
      <h1 class="text-2xl font-semibold text-ink-gray-9">Theme</h1>
      <p class="mt-1 text-base text-ink-gray-6">How your store looks, and what's on its built-in pages.</p>

      <div class="mt-6 rounded-lg border border-outline-gray-2 p-5">
        <div class="flex items-center gap-4">
          <div class="h-16 w-24 shrink-0 rounded bg-gradient-to-br from-amber-400 to-red-500" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-lg font-semibold text-ink-gray-9">Summer</span>
              <Badge label="Live" theme="green" />
            </div>
            <p class="text-sm text-ink-gray-6">Colours, fonts, header and footer</p>
          </div>
          <Button variant="solid" icon-left="lucide-paintbrush" label="Customize" @click="router.push('/themes/summer_theme/customize')" />
        </div>
        <div class="mt-4 flex flex-wrap gap-2 border-t border-outline-gray-1 pt-4">
          <span class="text-sm text-ink-gray-6">Pages it designs:</span>
          <span v-for="page in STORE_PAGES" :key="page.key" class="rounded bg-surface-gray-2 px-2 py-0.5 text-sm text-ink-gray-7">{{ page.title }}</span>
        </div>
      </div>

      <p class="mt-8 text-sm font-medium text-ink-gray-7">Other themes</p>
      <div class="mt-2 grid grid-cols-2 gap-3">
        <div v-for="name in ['Shop Default', 'Atelier']" :key="name" class="flex items-center justify-between rounded-lg border border-outline-gray-2 p-3">
          <span class="text-base text-ink-gray-8">{{ name }}</span>
          <Button size="sm" label="Preview" @click="toast.info(`Previewing ${name}`)" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="flex items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold text-ink-gray-9">Pages</h1>
          <p class="mt-1 text-base text-ink-gray-6">
            Extra pages for your store, like About us, a sale or a lookbook. You design them in Frappe Builder;
            your header, footer and colours are added for you.
          </p>
        </div>
        <Button variant="solid" icon-left="lucide-plus" label="New page" data-new-page-button @click="newPage = true" />
      </div>
      <div class="mt-6 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <PageRow
          v-for="page in pages"
          :key="page.name"
          icon="lucide-file"
          :title="page.title"
          :detail="`${page.route} · edited ${page.edited}`"
          :status="page.status"
          external
          @edit="toast.info('Opening Frappe Builder…')"
        />
      </div>
      <NewPage v-model:open="newPage" />
    </template>
  </DashboardFrame>
</template>
