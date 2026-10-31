<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, Textarea, TextInput, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardFrame from './DashboardFrame.vue'
import PageRow from './PageRow.vue'
import NewPage from './NewPage.vue'
import { pages } from './data.js'

// Variation C: pages split by what they are, not by tool. Text pages (about,
// FAQ, policies) are written right here, like today's Shop Web Page editor.
// Designed pages (campaigns) open in Builder. The theme stays as in A.
const router = useRouter()
const screen = ref('pages')
const newPage = ref(false)
const editing = ref(null)

const textPages = computed(() => pages.filter((page) => page.kind === 'text'))
const designedPages = computed(() => pages.filter((page) => page.kind === 'designed'))
</script>

<template>
  <DashboardFrame
    variant="C"
    :active="screen"
    :items="[{ key: 'theme', label: 'Theme', icon: 'lucide-palette' }, { key: 'pages', label: 'Pages', icon: 'lucide-files' }]"
    @navigate="(key) => ((screen = key), (editing = null))"
  >
    <template v-if="screen === 'theme'">
      <h1 class="text-2xl font-semibold text-ink-gray-9">Theme</h1>
      <p class="mt-1 text-base text-ink-gray-6">Same as variation A: the live theme and its built-in pages.</p>
      <Button class="mt-6" variant="solid" icon-left="lucide-paintbrush" label="Customize Summer" @click="router.push('/themes/summer_theme/customize')" />
    </template>

    <template v-else-if="editing">
      <button class="mb-4 flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-7" @click="editing = null">
        <span class="lucide-chevron-left size-3.5" aria-hidden="true" /> Pages
      </button>
      <div class="flex items-center gap-2">
        <h1 class="min-w-0 flex-1 text-2xl font-semibold text-ink-gray-9">{{ editing.title }}</h1>
        <Badge :label="editing.status" :theme="editing.status === 'Published' ? 'green' : 'gray'" />
      </div>
      <p class="mt-1 text-sm text-ink-gray-5">yourstore.com{{ editing.route }} · shown inside your theme</p>
      <div class="mt-6 space-y-4" data-text-editor>
        <TextInput :model-value="editing.title" />
        <Textarea
          :rows="12"
          model-value="We started as three friends and one print shop, with a rule: nothing gets made until someone wants it.&#10;&#10;Every tee, hoodie and poster is printed when you order it, so nothing sits in a warehouse and nothing gets thrown away."
        />
        <div class="flex gap-2">
          <Button variant="solid" label="Publish" @click="toast.success('Published')" />
          <Button label="Preview" @click="toast.info('Opens the page in the store')" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="flex items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold text-ink-gray-9">Pages</h1>
          <p class="mt-1 text-base text-ink-gray-6">Pages you add to your store, besides the ones your theme provides.</p>
        </div>
        <Button variant="solid" icon-left="lucide-plus" label="New page" data-new-page-button @click="newPage = true" />
      </div>

      <h2 class="mt-8 flex items-center gap-2 text-lg font-semibold text-ink-gray-9">
        <span class="lucide-file-text size-4 text-ink-gray-6" aria-hidden="true" /> Text pages
      </h2>
      <p class="text-sm text-ink-gray-6">About us, FAQ, policies. Written here, like a document.</p>
      <div class="mt-3 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <PageRow
          v-for="page in textPages"
          :key="page.name"
          icon="lucide-file-text"
          :title="page.title"
          :detail="`${page.route} · edited ${page.edited}`"
          :status="page.status"
          @edit="editing = page"
        />
      </div>

      <h2 class="mt-8 flex items-center gap-2 text-lg font-semibold text-ink-gray-9">
        <span class="lucide-palette size-4 text-ink-gray-6" aria-hidden="true" /> Designed pages
      </h2>
      <p class="text-sm text-ink-gray-6">Campaigns and landing pages. Laid out visually in Frappe Builder.</p>
      <div class="mt-3 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <PageRow
          v-for="page in designedPages"
          :key="page.name"
          icon="lucide-palette"
          :title="page.title"
          :detail="`${page.route} · edited ${page.edited}`"
          :status="page.status"
          action="Design"
          external
          @edit="toast.info('Opening Frappe Builder…')"
        />
      </div>
      <NewPage v-model:open="newPage" ask-kind />
    </template>
  </DashboardFrame>
</template>
