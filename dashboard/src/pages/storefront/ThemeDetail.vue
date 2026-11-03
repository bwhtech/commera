<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button, LoadingText, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import ResponsiveButton from '../../components/ResponsiveButton.vue'
import { themeKind, themeNote, useTheme } from '../../data/theme'
import { errorMessage } from '../../data/errors'

const route = useRoute()
const { themes, loadError, loading, load, activate } = useTheme()

onMounted(load)

const themeName = computed(() => String(route.params.theme))
const theme = computed(() => themes.value.find((candidate) => candidate.name === themeName.value) ?? null)
const liveTheme = computed(() => themes.value.find((candidate) => candidate.live) ?? null)

const details = computed(() => [
  { label: 'Type', value: theme.value.theme_type || 'Classic' },
  { label: 'Extends', value: theme.value.parent_theme || 'No parent theme' },
  { label: 'Settings', value: theme.value.theme_settings || 'None of its own', href: theme.value.settings_desk_url },
])

function confirmActivate() {
  const name = theme.value.theme_name
  const previous = liveTheme.value?.theme_name
  dialog.confirm({
    title: `Activate ${name}?`,
    message: previous
      ? `Shoppers see ${name} straight away. ${previous} becomes a draft and keeps all its changes.`
      : `Shoppers see ${name} straight away.`,
    confirmLabel: 'Activate',
    onConfirm: async () => {
      if (await activate(theme.value.name)) toast.success(`${name} is now the live theme`)
    },
  })
}
</script>

<template>
  <AppPageHeader
    :title="theme?.theme_name ?? themeName"
    back-to="/storefront/theme"
    :breadcrumbs="[
      { label: 'Themes', route: '/storefront/theme' },
      { label: theme?.theme_name ?? themeName },
    ]"
  >
    <template v-if="theme" #actions>
      <Button v-if="!theme.live" label="Activate" :loading="loading" @click="confirmActivate" />
      <Button
        v-if="theme.theme_type === 'Sections'"
        label="Customize"
        variant="solid"
        theme="gray"
        :route="{ name: 'StorefrontThemeEditor', params: { theme: theme.name } }"
      />
    </template>
  </AppPageHeader>

  <PageBody width="narrow">
    <LoadingText v-if="loading && !themes.length" />

    <EmptyState
      v-else-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load this theme"
      :description="errorMessage(loadError)"
    />

    <EmptyState
      v-else-if="!theme"
      icon="lucide-palette"
      title="Theme not found"
      description="It may have been removed along with the app that shipped it."
    >
      <Button variant="subtle" theme="gray" label="Back to themes" route="/storefront/theme" />
    </EmptyState>

    <div v-else class="space-y-8">
      <div class="flex items-center gap-4">
        <span class="grid h-16 w-24 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-6">
          <span class="lucide-palette size-5" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <h2 class="truncate text-xl font-semibold text-ink-gray-9">{{ theme.theme_name }}</h2>
            <Badge v-if="theme.live" label="Live" theme="green" variant="subtle" />
            <Badge v-else label="Draft" theme="gray" variant="subtle" />
          </div>
          <p class="mt-1 truncate text-sm text-ink-gray-5">{{ themeKind(theme) }} · {{ themeNote(theme) }}</p>
        </div>
      </div>

      <section>
        <h2 class="text-lg-semibold text-ink-gray-8">Details</h2>
        <dl class="mt-3 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-2">
          <div v-for="detail in details" :key="detail.label" class="flex items-center gap-4 px-4 py-3">
            <dt class="w-24 shrink-0 text-base text-ink-gray-5 sm:w-40">{{ detail.label }}</dt>
            <dd class="min-w-0 flex-1 break-words text-base text-ink-gray-8">{{ detail.value }}</dd>
            <ResponsiveButton
              v-if="detail.href"
              label="Open in Desk"
              icon="lucide-external-link"
              icon-position="right"
              variant="ghost"
              :href="detail.href"
            />
          </div>
        </dl>
        <p v-if="theme.theme_type === 'Sections'" class="mt-3 text-p-sm text-ink-gray-5">
          Colours, fonts and sections are edited in Customize.
        </p>
      </section>
    </div>
  </PageBody>
</template>
