<script setup>
import { computed } from 'vue'
import { useTheme } from '../../../data/theme'
import { draft, lookFor } from '../../../ia/onboarding'

const { themes, loading } = useTheme()

const themeNames = computed(() => themes.value.map((theme) => theme.name))
const choices = computed(() =>
  themes.value.map((theme) => ({ name: theme.name, label: theme.theme_name || theme.name, look: lookFor(theme.name, themeNames.value) })),
)
</script>

<template>
  <div v-if="loading && !choices.length" class="grid grid-cols-2 gap-3">
    <div v-for="index in 4" :key="index" class="h-28 animate-pulse rounded-5 bg-surface-gray-2" />
  </div>
  <div v-else class="grid grid-cols-2 gap-3">
    <button
      v-for="choice in choices"
      :key="choice.name"
      type="button"
      class="text-start transition-transform duration-150 ease-out-strong active:scale-[0.98]"
      :aria-pressed="draft.theme === choice.name"
      :data-onboarding-theme="choice.name"
      @click="draft.theme = choice.name"
    >
      <div
        class="h-28 overflow-hidden rounded-5 border transition-[border-color,box-shadow,transform] duration-200 ease-out-strong"
        :class="
          draft.theme === choice.name
            ? 'border-outline-gray-5 ring-1 ring-outline-gray-5'
            : 'border-outline-gray-2 hover:-translate-y-0.5 hover:border-outline-gray-3 motion-reduce:hover:translate-y-0'
        "
      >
        <!-- Scoped inside the frame so a dark look darkens the sketch, not the selection ring. -->
        <div class="h-full bg-surface-base p-3" :data-theme="choice.look.dark ? 'dark' : undefined">
          <div class="h-12" :class="[choice.look.hero, choice.look.radius]" />
          <div class="mt-2 grid grid-cols-4 gap-1.5">
            <span v-for="tile in 4" :key="tile" class="h-8" :class="[choice.look.tile, choice.look.radius]" />
          </div>
        </div>
      </div>
      <p class="mt-1.5 truncate px-0.5 text-sm text-ink-gray-7">{{ choice.label }}</p>
    </button>
  </div>
</template>
