<script setup>
import { ref } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardFrame from './DashboardFrame.vue'
import PageRow from './PageRow.vue'
import NewPage from './NewPage.vue'
import { STORE_PAGES, pages } from './data.js'

// Variation B: every page in one list, one Edit button each; the page decides
// which editor opens. Theme is only the look (which theme, colours, fonts).
const router = useRouter()
const screen = ref('pages')
const newPage = ref(false)
</script>

<template>
  <DashboardFrame
    variant="B"
    :active="screen"
    :items="[{ key: 'pages', label: 'Pages', icon: 'lucide-files' }, { key: 'theme', label: 'Look & feel', icon: 'lucide-palette' }]"
    @navigate="(key) => (screen = key)"
  >
    <template v-if="screen === 'pages'">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold text-ink-gray-9">Pages</h1>
          <p class="mt-1 text-base text-ink-gray-6">Everything shoppers can visit on your store.</p>
        </div>
        <Button variant="solid" icon-left="lucide-plus" label="New page" data-new-page-button @click="newPage = true" />
      </div>

      <h2 class="mt-8 text-lg font-semibold text-ink-gray-9">Store pages</h2>
      <p class="text-sm text-ink-gray-6">Every store has these. Rearrange their sections and change their text and images.</p>
      <div class="mt-3 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <PageRow
          v-for="page in STORE_PAGES"
          :key="page.key"
          :icon="page.icon"
          :title="page.title"
          :detail="page.detail"
          @edit="router.push({ path: '/themes/summer_theme/customize', query: { page: page.key === 'cart' ? 'index' : page.key } })"
        />
      </div>

      <h2 class="mt-8 text-lg font-semibold text-ink-gray-9">Your pages</h2>
      <p class="text-sm text-ink-gray-6">Pages you add, like About us or a sale. They open in Frappe Builder, where you design them freely.</p>
      <div class="mt-3 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
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

    <template v-else>
      <h1 class="text-2xl font-semibold text-ink-gray-9">Look &amp; feel</h1>
      <p class="mt-1 text-base text-ink-gray-6">Your theme sets colours, fonts, header and footer on every page, including the ones you design in Builder.</p>
      <div class="mt-6 flex items-center gap-4 rounded-lg border border-outline-gray-2 p-5">
        <div class="h-16 w-24 shrink-0 rounded bg-gradient-to-br from-amber-400 to-red-500" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-lg font-semibold text-ink-gray-9">Summer</span>
            <Badge label="Live" theme="green" />
          </div>
          <p class="text-sm text-ink-gray-6">To change what's on a page, go to Pages.</p>
        </div>
        <Button label="Colours & fonts" icon-left="lucide-paintbrush" @click="router.push('/themes/summer_theme/customize')" />
        <Button label="Change theme" @click="toast.info('Theme gallery')" />
      </div>
    </template>
  </DashboardFrame>
</template>
