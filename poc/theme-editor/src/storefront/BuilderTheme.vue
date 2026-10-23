<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Select, dialog, toast } from 'frappe-ui'
import StorefrontShell from './StorefrontShell.vue'
import ThemeThumb from './ThemeThumb.vue'
import { BUILDER_THEME_PAGES, themes } from './data.js'

// "Edit theme" for a Builder theme. It is the same place as for a sections
// theme (Themes → Edit theme), but the pages open in Builder and the theme's
// colours and fonts are set here, so content pages and every Builder page
// share them.
const route = useRoute()
const router = useRouter()
const theme = computed(() => themes.find((candidate) => candidate.name === route.params.theme))

const STATUS = {
  empty: { label: 'Not designed yet', theme: 'gray', action: 'Design in Builder' },
  draft: { label: 'Drafted', theme: 'orange', action: 'Edit in Builder' },
  designed: { label: 'Designed', theme: 'green', action: 'Edit in Builder' },
}

const missing = computed(() => BUILDER_THEME_PAGES.filter((page) => page.required && theme.value.pages[page.key] !== 'designed'))

// Builder opens in a new tab. In the prototype, coming back counts as having
// designed the page, so the checklist can be walked through.
function openInBuilder(page) {
  toast.info(`Opening ${page.title} in Frappe Builder`)
  theme.value.pages[page.key] = 'designed'
}

function publish() {
  dialog.confirm({
    title: `Publish ${theme.value.title}?`,
    message: 'It becomes your live store. Your current theme moves to Draft themes.',
    confirmLabel: 'Publish',
    onConfirm: () => {
      themes.forEach((candidate) => (candidate.live = candidate === theme.value))
      toast.success(`${theme.value.title} is live`)
      router.push('/storefront/themes')
    },
  })
}

const fonts = [
  { value: 'Inter', label: 'Inter' },
  { value: 'Georgia', label: 'Georgia (serif)' },
  { value: 'Space Grotesk', label: 'Space Grotesk' },
]
</script>

<template>
  <StorefrontShell>
    <template v-if="theme">
      <button class="mb-3 flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-7" @click="router.push('/storefront/themes')">
        <span class="lucide-chevron-left size-3.5" aria-hidden="true" /> Themes
      </button>
      <div class="flex items-center gap-4">
        <ThemeThumb :theme="theme" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <h1 class="text-2xl font-semibold text-ink-gray-9">{{ theme.title }}</h1>
            <Badge :label="theme.live ? 'Live' : 'Draft'" :theme="theme.live ? 'green' : 'gray'" />
          </div>
          <p class="text-sm text-ink-gray-6">Designed in Frappe Builder</p>
        </div>
        <Button label="Preview" icon-left="lucide-eye" @click="toast.info('Opens the store with this theme')" />
        <Button v-if="!theme.live" variant="solid" label="Publish" :disabled="missing.length > 0" data-publish-theme @click="publish" />
      </div>

      <div class="mt-8 flex items-end justify-between">
        <div>
          <h2 class="text-lg font-semibold text-ink-gray-9">Theme pages</h2>
          <p class="text-sm text-ink-gray-6">Each opens in Frappe Builder. Your products, collections and content pages fill them in.</p>
        </div>
        <p class="text-sm text-ink-gray-6" data-ready>
          {{ missing.length ? `${missing.length} left to design before publishing` : 'Ready to publish' }}
        </p>
      </div>
      <div class="mt-3 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <div v-for="page in BUILDER_THEME_PAGES" :key="page.key" class="flex items-center gap-4 px-4 py-3" :data-theme-page="page.key">
          <span :class="page.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <p class="text-base font-medium text-ink-gray-9">
              {{ page.title }}
              <span v-if="!page.required" class="text-sm font-normal text-ink-gray-5">· optional</span>
            </p>
            <p class="text-sm text-ink-gray-5">{{ page.detail }}</p>
          </div>
          <Badge :label="STATUS[theme.pages[page.key]].label" :theme="STATUS[theme.pages[page.key]].theme" />
          <Button :label="STATUS[theme.pages[page.key]].action" icon-right="lucide-arrow-up-right" @click="openInBuilder(page)" />
        </div>
      </div>

      <h2 class="mt-8 text-lg font-semibold text-ink-gray-9">Theme settings</h2>
      <p class="text-sm text-ink-gray-6">Colours and fonts for the whole theme. Builder pages and your content pages both use them.</p>
      <div class="mt-3 space-y-4 rounded-lg border border-outline-gray-2 p-4">
        <div class="grid grid-cols-3 gap-4">
          <label v-for="key in ['accent', 'text', 'background']" :key="key" class="flex items-center justify-between gap-3 text-sm text-ink-gray-7">
            {{ { accent: 'Accent colour', text: 'Text colour', background: 'Background' }[key] }}
            <input v-model="theme.settings[key]" type="color" class="h-7 w-10 cursor-pointer rounded border border-outline-gray-2" />
          </label>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1">
            <span class="text-sm text-ink-gray-7">Heading font</span>
            <Select v-model="theme.settings.heading_font" class="w-full" :options="fonts" />
          </div>
          <div class="space-y-1">
            <span class="text-sm text-ink-gray-7">Body font</span>
            <Select v-model="theme.settings.body_font" class="w-full" :options="fonts" />
          </div>
        </div>
      </div>
    </template>
    <p v-else class="text-ink-gray-6">Theme not found.</p>
  </StorefrontShell>
</template>
