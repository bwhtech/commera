<script setup>
/**
 * The live theme and the settings that theme ships of its own — over a preview of the actual
 * storefront home page, re-rendered by the server on every save.
 */
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Skeleton, toast } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import ChromePreview from './ChromePreview.vue'
import ThemeField from './ThemeField.vue'
import { useTheme } from '../../data/theme'
import { errorMessage } from '../../data/errors'

const { themes, settings, previewToken, loadError, loading, load, mutate } = useTheme()

onMounted(load)

const isMobile = useMediaQuery('(max-width: 639.98px)')
const previewCollapsed = ref(isMobile.value)

const liveTheme = computed(() => themes.value.find((theme) => theme.live) ?? null)

// What the pane frames. Held by name, not by row, so it survives every reload of the list;
// unset - or pointing at a theme that has since gone - it falls back to whatever is live.
const selectedName = ref(null)
const previewedTheme = computed(
  () => themes.value.find((theme) => theme.name === selectedName.value) ?? liveTheme.value,
)

const previewParams = computed(() =>
  previewedTheme.value ? { theme: previewedTheme.value.name } : {},
)

const previewTitle = computed(() => {
  if (!previewedTheme.value || previewedTheme.value.live) return 'Storefront preview'
  return `Preview: ${previewedTheme.value.theme_name}`
})

// What a theme is, in the only terms this screen knows: what it builds on.
function themeNote(theme) {
  if (theme.parent_theme) return `Extends ${theme.parent_theme}`
  return 'Base theme — the one every other theme builds on'
}

async function activate(theme) {
  if (await mutate('activate_theme', { theme: theme.name })) {
    selectedName.value = theme.name
    toast.success(`${theme.theme_name} is now the live theme`)
  }
}

async function saveSetting(field, value) {
  if (await mutate('save_theme_settings', { [field.fieldname]: value })) {
    toast.success(`${field.label} saved`)
  }
}
</script>

<template>
  <div>
    <div v-if="loading && !themes.length" class="gap-6 lg:flex lg:items-start" aria-hidden="true">
      <section class="w-full shrink-0 lg:w-[22rem]">
        <Skeleton class="h-5 w-36 rounded-4" />
        <Skeleton class="mt-2 h-3.5 w-64 max-w-full rounded-4" />
        <div class="mt-3 space-y-2">
          <div v-for="card in 3" :key="card" class="flex items-center gap-3 rounded-5 border border-outline-gray-1 p-3">
            <Skeleton class="size-9 shrink-0 rounded-4" />
            <div class="min-w-0 flex-1">
              <Skeleton class="h-4 w-32 rounded-4" />
              <Skeleton class="mt-2 h-3.5 w-44 max-w-full rounded-4" />
            </div>
            <Skeleton class="h-5 w-12 shrink-0 rounded-full" />
          </div>
        </div>
      </section>

      <div class="mt-8 min-w-0 flex-1 lg:mt-0">
        <Skeleton class="h-5 w-48 rounded-4" />
        <div v-for="group in 2" :key="group" class="mt-4">
          <Skeleton class="h-3.5 w-24 rounded-4" />
          <div class="mt-2 grid gap-4 sm:grid-cols-2">
            <div v-for="field in 4" :key="field">
              <Skeleton class="h-3.5 w-28 rounded-4" />
              <Skeleton class="mt-1.5 h-7 w-full rounded-4" />
            </div>
          </div>
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

    <div v-else class="gap-6 lg:flex lg:items-start">
      <section class="w-full shrink-0 lg:w-[22rem]">
        <h2 class="text-lg-semibold text-ink-gray-8">Installed themes</h2>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Pick one to preview it below. Only the live theme's own settings can be edited.
        </p>
        <div class="mt-3 space-y-2">
          <div
            v-for="theme in themes"
            :key="theme.name"
            class="flex items-center gap-3 rounded-5 border p-3"
            :class="
              theme.name === previewedTheme?.name
                ? 'border-outline-gray-3 bg-surface-gray-2'
                : 'border-outline-gray-1'
            "
          >
            <button
              type="button"
              class="flex min-w-0 flex-1 items-center gap-3 text-left"
              :aria-pressed="theme.name === previewedTheme?.name"
              @click="selectedName = theme.name"
            >
              <span
                class="grid size-9 shrink-0 place-items-center rounded-4 bg-surface-base text-ink-gray-6"
              >
                <span class="lucide-palette size-4" aria-hidden="true" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-base text-ink-gray-8">{{ theme.theme_name }}</p>
                <p class="mt-1 truncate text-sm text-ink-gray-5">
                  {{ themeNote(theme) }}
                </p>
              </div>
            </button>
            <Badge v-if="theme.live" label="Live" theme="green" variant="subtle" />
            <Button v-else label="Activate" :loading="loading" @click="activate(theme)" />
          </div>
        </div>
      </section>

      <div class="mt-8 min-w-0 flex-1 space-y-8 lg:mt-0">
        <section v-if="settings.doctype">
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-lg-semibold text-ink-gray-8">{{ liveTheme?.theme_name }} settings</h2>
            <Button
              v-if="settings.desk_url"
              label="Open in Desk"
              icon-right="lucide-external-link"
              variant="ghost"
              :href="settings.desk_url"
            />
          </div>

          <div v-for="group in settings.groups" :key="group.label" class="mt-4">
            <p class="text-sm text-ink-gray-5">{{ group.label }}</p>
            <div class="mt-2 grid gap-4 sm:grid-cols-2">
              <ThemeField
                v-for="field in group.fields"
                :key="field.fieldname"
                :field="field"
                :disabled="loading"
                @commit="saveSetting(field, $event)"
              />
            </div>
          </div>

          <!-- Slides, banners and pinned products are rows of their own, not fields; this screen
               says where they live rather than pretending it can edit them. -->
          <div v-if="settings.child_tables.length" class="mt-6">
            <p class="text-sm text-ink-gray-5">Content this theme lists</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <a
                v-for="table in settings.child_tables"
                :key="table.fieldname"
                :href="settings.desk_url"
                target="_blank"
                rel="noopener"
                class="flex items-center gap-2 rounded-5 border border-outline-gray-1 px-3 py-2 text-base text-ink-gray-7 hover:bg-surface-gray-2"
              >
                {{ table.label }}
                <Badge :label="String(table.count)" theme="gray" variant="subtle" />
              </a>
            </div>
          </div>
        </section>

        <section v-else>
          <h2 class="text-lg-semibold text-ink-gray-8">Theme settings</h2>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            {{ liveTheme?.theme_name ?? 'The live theme' }} ships no settings of its own.
          </p>
        </section>

        <section>
          <h2 class="text-lg-semibold text-ink-gray-8">Layout</h2>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            Header, footer and page content live in Navigation and Pages — this screen owns the live
            theme and the settings it ships.
          </p>
          <div class="mt-3 flex gap-2">
            <Button label="Edit navigation" route="/storefront/navigation" />
            <Button label="Edit pages" route="/storefront/pages" />
          </div>
        </section>
      </div>
    </div>

    <ChromePreview
      v-model:collapsed="previewCollapsed"
      :token="previewToken"
      path="/theme_editor_preview"
      :title="previewTitle"
      :params="previewParams"
      selector="body"
    />
  </div>
</template>
