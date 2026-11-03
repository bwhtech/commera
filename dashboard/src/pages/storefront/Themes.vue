<script setup>
import { computed, onMounted } from 'vue'
import { Badge, Skeleton } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import { themeKind, themeNote, useTheme } from '../../data/theme'
import { errorMessage } from '../../data/errors'

const { themes, loadError, loading, load } = useTheme()

onMounted(load)

const liveTheme = computed(() => themes.value.find((theme) => theme.live) ?? null)
const draftThemes = computed(() => themes.value.filter((theme) => !theme.live))

function detailRoute(theme) {
  return { name: 'StorefrontThemeDetail', params: { theme: theme.name } }
}
</script>

<template>
  <AppPageHeader title="Themes" />

  <PageBody width="wide">
    <p class="text-p-sm text-ink-gray-5">Your theme decides how every page of your store looks.</p>

    <div v-if="loading && !themes.length" class="mt-6" aria-hidden="true">
      <Skeleton class="h-3.5 w-24 rounded-4" />
      <div class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 p-4">
        <Skeleton class="h-16 w-24 shrink-0 rounded-4" />
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
      <section v-if="liveTheme" class="mt-6">
        <h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Live theme</h2>
        <RouterLink
          :to="detailRoute(liveTheme)"
          class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 p-4 hover:bg-surface-gray-1"
          data-live-theme
        >
          <span class="grid h-16 w-24 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-6">
            <span class="lucide-palette size-5" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2">
              <span class="truncate text-lg-semibold text-ink-gray-9">{{ liveTheme.theme_name }}</span>
              <Badge label="Live" theme="green" variant="subtle" />
            </span>
            <span class="mt-1 block truncate text-sm text-ink-gray-5">
              {{ themeKind(liveTheme) }} · {{ themeNote(liveTheme) }}
            </span>
          </span>
          <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
        </RouterLink>
      </section>

      <section v-if="draftThemes.length" class="mt-8">
        <h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Draft themes</h2>
        <p class="text-p-sm text-ink-gray-5">Shoppers only see the live theme.</p>
        <div class="mt-2 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-2">
          <RouterLink
            v-for="theme in draftThemes"
            :key="theme.name"
            :to="detailRoute(theme)"
            class="flex items-center gap-4 px-4 py-3 first:rounded-t-5 last:rounded-b-5 hover:bg-surface-gray-1"
            :data-draft-theme="theme.name"
          >
            <span class="grid h-10 w-16 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-6">
              <span class="lucide-palette size-4" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-base text-ink-gray-8">{{ theme.theme_name }}</span>
              <span class="mt-1 block truncate text-sm text-ink-gray-5">
                {{ themeKind(theme) }} · {{ themeNote(theme) }}
              </span>
            </span>
            <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
          </RouterLink>
        </div>
      </section>
    </template>
  </PageBody>
</template>
