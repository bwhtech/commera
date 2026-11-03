<script setup>
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'

const props = defineProps({
  theme: { type: Object, required: true },
  featured: { type: Boolean, default: false },
  activating: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

defineEmits(['activate'])

const isClassic = computed(() => props.theme.theme_type !== 'Sections')
const muted = computed(() => isClassic.value && !props.theme.live)
const meta = computed(() => (isClassic.value ? props.theme.source : `Built with sections · ${props.theme.source}`))
const editorRoute = computed(() =>
  isClassic.value ? null : { name: 'StorefrontThemeEditor', params: { theme: props.theme.name } },
)
</script>

<template>
  <div
    class="relative flex items-center gap-3 sm:gap-4"
    :class="[featured ? 'px-4 py-5' : 'px-4 py-3', editorRoute ? 'hover:bg-surface-gray-1' : 'cursor-default']"
  >
    <span
      class="aspect-[16/10] shrink-0 rounded-4 bg-surface-gray-3"
      :class="[featured ? 'w-28 sm:w-44' : 'w-16 sm:w-20', { 'opacity-50': muted }]"
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
      label="Switch Theme"
      :loading="activating"
      :disabled="disabled"
      @click="$emit('activate', theme)"
    />
    <span
      class="lucide-chevron-right size-4 shrink-0 text-ink-gray-5"
      :class="{ invisible: !editorRoute }"
      aria-hidden="true"
    />
  </div>
</template>
