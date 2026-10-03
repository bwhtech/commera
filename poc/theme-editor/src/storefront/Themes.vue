<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dropdown, dialog, toast } from 'frappe-ui'
import StorefrontShell from './StorefrontShell.vue'
import ThemeThumb from './ThemeThumb.vue'
import CreateBuilderTheme from './CreateBuilderTheme.vue'
import { themes } from './data.js'

const router = useRouter()
const live = computed(() => themes.find((theme) => theme.live))
const drafts = computed(() => themes.filter((theme) => !theme.live))
const creating = ref(false)

const kindLabel = (theme) => (theme.kind === 'builder' ? 'Designed in Frappe Builder' : 'Built with sections')

// Sections themes open the section editor; Builder themes open their page list.
const editTheme = (theme) =>
  router.push(theme.kind === 'builder' ? `/storefront/themes/${theme.name}` : `/themes/${theme.name}/customize`)

function publish(theme) {
  dialog.confirm({
    title: `Publish ${theme.title}?`,
    message: `${theme.title} becomes your live store. ${live.value.title} moves to Draft themes, with all its changes kept.`,
    confirmLabel: 'Publish',
    onConfirm: () => {
      themes.forEach((candidate) => (candidate.live = candidate === theme))
      toast.success(`${theme.title} is live`)
    },
  })
}

const menu = (theme) => [
  { label: 'Preview', icon: 'lucide-eye', onClick: () => toast.info(`Previewing ${theme.title}`) },
  { label: 'Rename', icon: 'lucide-pencil', onClick: () => toast.info('Rename') },
  { label: 'Duplicate', icon: 'lucide-copy', onClick: () => toast.info(`Copy of ${theme.title} added to drafts`) },
  ...(theme.live ? [] : [{ label: 'Remove', icon: 'lucide-trash-2', theme: 'red', onClick: () => toast.info('Removed') }]),
]
</script>

<template>
  <StorefrontShell>
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Themes</h1>
        <p class="mt-1 text-base text-ink-gray-6">Your theme decides how every page of your store looks.</p>
      </div>
      <Dropdown
        :options="[
          { label: 'Create with Frappe Builder', icon: 'lucide-blocks', onClick: () => (creating = true) },
          { label: 'Get themes from apps', icon: 'lucide-store', onClick: () => toast.info('Opens Settings → Installed apps → Discover') },
        ]"
      >
        <Button icon-left="lucide-plus" icon-right="lucide-chevron-down" label="Add theme" data-add-theme />
      </Dropdown>
    </div>

    <p class="mt-8 text-sm font-medium uppercase tracking-wide text-ink-gray-5">Live theme</p>
    <div v-if="live" class="mt-2 flex items-center gap-5 rounded-lg border border-outline-gray-2 p-5" data-live-theme>
      <ThemeThumb :theme="live" size="lg" />
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span class="text-xl font-semibold text-ink-gray-9">{{ live.title }}</span>
          <Badge label="Live" theme="green" />
        </div>
        <p class="mt-1 text-sm text-ink-gray-6">{{ kindLabel(live) }} · {{ live.source }}</p>
        <p class="text-sm text-ink-gray-5">{{ live.saved }}</p>
      </div>
      <Dropdown :options="menu(live)"><Button variant="ghost" icon="lucide-ellipsis" label="More" /></Dropdown>
      <Button variant="solid" icon-left="lucide-paintbrush" label="Edit theme" data-edit-live @click="editTheme(live)" />
    </div>

    <p class="mt-8 text-sm font-medium uppercase tracking-wide text-ink-gray-5">Draft themes</p>
    <p class="text-sm text-ink-gray-6">Edit and preview these safely; shoppers only see the live theme.</p>
    <div class="mt-2 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
      <div v-for="theme in drafts" :key="theme.name" class="flex items-center gap-4 px-4 py-3" :data-draft-theme="theme.name">
        <ThemeThumb :theme="theme" />
        <div class="min-w-0 flex-1">
          <p class="text-base font-medium text-ink-gray-9">{{ theme.title }}</p>
          <p class="text-sm text-ink-gray-5">{{ kindLabel(theme) }} · {{ theme.saved }}</p>
        </div>
        <Dropdown :options="menu(theme)"><Button variant="ghost" icon="lucide-ellipsis" label="More" /></Dropdown>
        <Button label="Publish" @click="publish(theme)" />
        <Button label="Edit theme" @click="editTheme(theme)" />
      </div>
    </div>

    <CreateBuilderTheme v-model:open="creating" @created="(theme) => editTheme(theme)" />
  </StorefrontShell>
</template>
