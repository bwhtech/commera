<script setup>
import { computed, onMounted, ref } from 'vue'
import { Skeleton, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import ThemeRow from '../../components/storefront/ThemeRow.vue'
import { useTheme } from '../../data/theme'
import { captureMissingThumbnails } from '../../data/storePreview'
import { errorMessage } from '../../data/errors'

const { themes, loadError, loading, load, activate } = useTheme()

onMounted(async () => {
  await load()
  captureMissingThumbnails(themes.value, load)
})

const activatingName = ref(null)

const liveTheme = computed(() => themes.value.find((theme) => theme.live) ?? null)
const libraryThemes = computed(() => themes.value.filter((theme) => !theme.live))

function confirmActivate(theme) {
  const previous = liveTheme.value?.theme_name
  dialog.confirm({
    title: `Switch to ${theme.theme_name}?`,
    message: previous
      ? `Shoppers see ${theme.theme_name} straight away. ${previous} moves to the theme library and keeps all its changes.`
      : `Shoppers see ${theme.theme_name} straight away.`,
    confirmLabel: 'Switch Theme',
    onConfirm: async () => {
      activatingName.value = theme.name
      try {
        if (await activate(theme.name)) toast.success(`${theme.theme_name} is now the live theme`)
      } finally {
        activatingName.value = null
      }
    },
  })
}
</script>

<template>
  <AppPageHeader title="Themes" />

  <PageBody width="wide">
    <div v-if="loading && !themes.length" aria-hidden="true">
      <Skeleton class="h-3.5 w-24 rounded-4" />
      <div class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 px-4 py-5">
        <Skeleton class="aspect-[16/10] w-28 shrink-0 rounded-4 sm:w-44" />
        <div class="min-w-0 flex-1">
          <Skeleton class="h-4 w-32 rounded-4" />
          <Skeleton class="mt-2 h-3.5 w-56 max-w-full rounded-4" />
        </div>
      </div>
    </div>

    <EmptyState
      v-else-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load themes"
      :description="errorMessage(loadError)"
    />

    <EmptyState
      v-else-if="!themes.length"
      icon="lucide-palette"
      title="No themes installed"
      description="A theme ships with the app it belongs to. Install one to style the storefront."
    />

    <template v-else>
      <section v-if="liveTheme" data-live-theme>
        <h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Live theme</h2>
        <div class="mt-2 overflow-hidden rounded-5 border border-outline-gray-2">
          <ThemeRow :theme="liveTheme" featured />
        </div>
      </section>

      <section v-if="libraryThemes.length" class="mt-8">
        <h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Theme library</h2>
        <p class="text-p-sm text-ink-gray-5">Shoppers only see the live theme.</p>
        <div class="mt-2 divide-y divide-outline-gray-1 overflow-hidden rounded-5 border border-outline-gray-2">
          <ThemeRow
            v-for="theme in libraryThemes"
            :key="theme.name"
            :theme="theme"
            :activating="activatingName === theme.name"
            :disabled="Boolean(activatingName)"
            :data-library-theme="theme.name"
            @activate="confirmActivate"
          />
        </div>
      </section>
    </template>
  </PageBody>
</template>
