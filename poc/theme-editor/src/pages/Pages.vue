<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dropdown, toast } from 'frappe-ui'
import { TEMPLATES } from '../theme/schemas.js'
import { BUILDER_PAGES, builderUrl } from '../theme/builder.js'
import { openBuilder } from '../editor/openBuilder.js'
import NewPageDialog from '../editor/NewPageDialog.vue'
import StorefrontNav from './StorefrontNav.vue'

// Every storefront page in one list. Theme pages open the section editor;
// Builder pages open Builder, and can also be previewed in the theme editor
// to check how they sit inside the store's header and footer.
const router = useRouter()
const showNewPage = ref(false)
const liveTheme = 'summer_theme'

const customize = (page) => router.push({ path: `/themes/${liveTheme}/customize`, query: { page } })
</script>

<template>
  <div class="mx-auto max-w-4xl px-6 py-10">
    <StorefrontNav />
    <div class="mt-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Pages</h1>
        <p class="mt-1 text-base text-ink-gray-6">Theme pages are arranged in the theme editor. Free-form pages are built in Frappe Builder.</p>
      </div>
      <Button variant="solid" icon-left="lucide-plus" label="New page" data-new-page @click="showNewPage = true" />
    </div>

    <div class="mt-6 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
      <div v-for="template in TEMPLATES" :key="template.value" class="flex items-center gap-4 px-4 py-3">
        <span :class="template.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-base font-medium text-ink-gray-9">{{ template.label }}</p>
          <p class="text-sm text-ink-gray-5">Summer theme · sections</p>
        </div>
        <Badge label="Theme page" theme="gray" />
        <Button icon-left="lucide-settings-2" label="Customize" @click="customize(template.value)" />
      </div>

      <div v-for="page in BUILDER_PAGES" :key="page.name" class="flex items-center gap-4 px-4 py-3" :data-builder-row="page.name">
        <span class="lucide-blocks size-4 text-ink-teal-4" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-base font-medium text-ink-gray-9">{{ page.title }}</p>
          <p class="text-sm text-ink-gray-5">{{ page.route }} · edited {{ page.edited }}</p>
        </div>
        <Badge :label="page.status" :theme="page.status === 'Published' ? 'green' : 'gray'" />
        <Badge label="Builder" theme="teal" />
        <Dropdown
          :options="[
            { label: 'Preview in theme editor', icon: 'lucide-eye', onClick: () => customize(`builder:${page.name}`) },
            { label: 'View live page', icon: 'lucide-external-link', onClick: () => toast.info(`Opens ${page.route}`) },
          ]"
        >
          <Button variant="ghost" icon="lucide-ellipsis" label="More" />
        </Dropdown>
        <Button
          icon-left="lucide-pencil"
          label="Edit in Builder"
          @click="openBuilder(builderUrl('page', { name: page.name }), page.title)"
        />
      </div>
    </div>

    <NewPageDialog v-model:open="showNewPage" />
  </div>
</template>
