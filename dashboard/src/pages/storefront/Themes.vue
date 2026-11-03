<script setup>
import { computed, onMounted, ref } from 'vue'
import { createReusableTemplate } from '@vueuse/core'
import { Badge, Button, Dropdown, Skeleton, dialog, toast } from 'frappe-ui'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import { themeKind, useTheme } from '../../data/theme'
import { errorMessage } from '../../data/errors'

const { themes, loadError, loading, load, activate } = useTheme()

onMounted(load)

const [DefineThemeRow, ThemeRow] = createReusableTemplate()

const activatingName = ref(null)

const liveTheme = computed(() => themes.value.find((theme) => theme.live) ?? null)
const libraryThemes = computed(() => themes.value.filter((theme) => !theme.live))

function openInNewTab(url) {
  window.open(url, '_blank', 'noopener')
}

function menuOptions(theme) {
  return [
    theme.settings_desk_url && {
      label: 'Open settings in Desk',
      icon: 'lucide-sliders-horizontal',
      onClick: () => openInNewTab(theme.settings_desk_url),
    },
    { label: 'Open theme in Desk', icon: 'lucide-external-link', onClick: () => openInNewTab(theme.desk_url) },
  ].filter(Boolean)
}

function confirmActivate(theme) {
  const previous = liveTheme.value?.theme_name
  dialog.confirm({
    title: `Activate ${theme.theme_name}?`,
    message: previous
      ? `Shoppers see ${theme.theme_name} straight away. ${previous} moves to the theme library and keeps all its changes.`
      : `Shoppers see ${theme.theme_name} straight away.`,
    confirmLabel: 'Activate',
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
  <DefineThemeRow v-slot="{ theme, featured }">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-3">
      <div class="flex min-w-0 flex-1 basis-56 items-center gap-4">
        <span
          class="grid shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-5"
          :class="featured ? 'h-20 w-32' : 'h-12 w-20'"
        >
          <span class="lucide-palette size-5" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="truncate text-ink-gray-9" :class="featured ? 'text-lg-semibold' : 'text-base font-medium'">
              {{ theme.theme_name }}
            </span>
            <Badge v-if="theme.live" label="Live" theme="green" variant="subtle" />
          </div>
          <p class="mt-1 text-sm text-ink-gray-5">{{ themeKind(theme) }} · {{ theme.source }}</p>
        </div>
      </div>
      <div class="ml-auto flex shrink-0 items-center gap-2">
        <Dropdown :options="menuOptions(theme)" placement="right">
          <Button variant="ghost" icon="lucide-ellipsis" :label="`More actions for ${theme.theme_name}`" />
        </Dropdown>
        <Button
          v-if="!theme.live"
          label="Activate"
          :loading="activatingName === theme.name"
          :disabled="Boolean(activatingName)"
          @click="confirmActivate(theme)"
        />
        <Button
          v-if="theme.theme_type === 'Sections'"
          label="Customize"
          :variant="featured ? 'solid' : 'subtle'"
          theme="gray"
          :route="{ name: 'StorefrontThemeEditor', params: { theme: theme.name } }"
        />
      </div>
    </div>
  </DefineThemeRow>

  <PageBody width="wide">
    <div v-if="loading && !themes.length" aria-hidden="true">
      <Skeleton class="h-3.5 w-24 rounded-4" />
      <div class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 p-5">
        <Skeleton class="h-20 w-32 shrink-0 rounded-4" />
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
        <div class="mt-2 rounded-5 border border-outline-gray-2 p-5">
          <ThemeRow :theme="liveTheme" :featured="true" />
        </div>
      </section>

      <section v-if="libraryThemes.length" class="mt-8">
        <h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Theme library</h2>
        <p class="text-p-sm text-ink-gray-5">Shoppers only see the live theme.</p>
        <div class="mt-2 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-2">
          <div v-for="theme in libraryThemes" :key="theme.name" class="px-4 py-3" :data-library-theme="theme.name">
            <ThemeRow :theme="theme" />
          </div>
        </div>
      </section>
    </template>
  </PageBody>
</template>
