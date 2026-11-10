<script setup>
import { computed } from 'vue'
import { Badge, Button, useColorScheme } from 'frappe-ui'
import Thumb from '../Thumb.vue'
import ResponsiveButton from '../ResponsiveButton.vue'

const props = defineProps({
  theme: { type: Object, required: true },
  featured: { type: Boolean, default: false },
  activating: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

defineEmits(['activate'])

const { resolvedColorScheme } = useColorScheme()

const isBuilder = computed(() => props.theme.theme_type === 'Builder')
const isClassic = computed(() => props.theme.theme_type !== 'Sections' && !isBuilder.value)
const muted = computed(() => isClassic.value && !props.theme.live)
const META_PREFIXES = { Sections: 'Built with sections', Builder: 'Built with Frappe Builder' }
const meta = computed(() => {
  const prefix = META_PREFIXES[props.theme.theme_type]
  return prefix ? `${prefix} · ${props.theme.source}` : props.theme.source
})
const editorRoute = computed(() =>
  props.theme.theme_type === 'Sections' ? { name: 'StorefrontThemeEditor', params: { theme: props.theme.name } } : null,
)
const thumbnail = computed(() =>
  resolvedColorScheme.value === 'dark' && props.theme.thumbnail_dark ? props.theme.thumbnail_dark : props.theme.thumbnail,
)
const imageSize = computed(() => (props.featured ? 'aspect-[16/10] w-full sm:w-60' : 'aspect-[16/10] w-28 sm:w-40'))
</script>

<template>
  <div
    class="relative flex gap-3 sm:items-center sm:gap-4"
    :class="[
      featured ? 'flex-col px-4 py-5 sm:flex-row' : 'items-center px-4 py-3',
      editorRoute ? 'hover:bg-surface-gray-1' : 'cursor-default',
    ]"
  >
    <Thumb
      v-if="thumbnail"
      :image="thumbnail"
      :size="imageSize"
      class="border border-outline-gray-2 object-top"
      :class="{ 'opacity-50': muted }"
      data-theme-thumbnail
    />
    <span
      v-else
      class="shrink-0 rounded-4 bg-surface-gray-3"
      :class="[imageSize, { 'opacity-50': muted }]"
      aria-hidden="true"
    />
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <RouterLink
          v-if="editorRoute"
          :to="editorRoute"
          :aria-label="`Customize ${theme.theme_name}`"
          class="truncate text-ink-gray-9 after:absolute after:inset-0 after:rounded-[inherit] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-outline-gray-3"
          :class="featured ? 'text-lg-semibold' : 'text-base font-medium'"
        >
          {{ theme.theme_name }}
        </RouterLink>
        <span
          v-else
          class="truncate"
          :class="[featured ? 'text-lg-semibold' : 'text-base font-medium', muted ? 'text-ink-gray-5' : 'text-ink-gray-9']"
        >
          {{ theme.theme_name }}
        </span>
        <Badge v-if="theme.live" label="Live" theme="green" variant="subtle" />
        <Badge v-if="isClassic" label="Classic" theme="gray" variant="subtle" />
      </div>
      <p class="mt-1 text-sm sm:truncate" :class="muted ? 'text-ink-gray-4' : 'text-ink-gray-5'">{{ meta }}</p>
    </div>
    <Button
      v-if="!theme.live && !theme.is_base"
      class="relative z-10"
      aria-label="Switch Theme"
      :loading="activating"
      :disabled="disabled"
      @click="$emit('activate', theme)"
    >
      <span class="sm:hidden">Switch</span>
      <span class="hidden sm:inline">Switch Theme</span>
    </Button>
    <ResponsiveButton
      v-if="isBuilder && theme.builder_editor_url"
      label="Edit in Builder"
      icon="lucide-external-link"
      icon-position="right"
      :href="theme.builder_editor_url"
    />
    <span
      class="lucide-chevron-right size-4 shrink-0 text-ink-gray-5"
      :class="{ invisible: !editorRoute, 'hidden sm:block': featured }"
      aria-hidden="true"
    />
  </div>
</template>
