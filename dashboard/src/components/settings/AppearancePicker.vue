<script setup>
/**
 * Light, dark, or follow the device. A preference of this browser, not of the store — which is
 * why it sits with the personal settings and nowhere near the storefront theme.
 *
 * Ours rather than frappe-ui's ThemeSwitcher: that component is deprecated in favour of
 * `useColorScheme` (it says so itself on mount), marks the chosen card with three extra pixels
 * of border weight — which does not read as chosen at all — and exposes no slot to change it,
 * so the only way to fit it here was to reach into its internals with CSS.
 *
 * Native radios rather than a listbox: the browser gives arrow-key movement, the roving tab
 * stop and the announced group for free, and all this screen adds is what the cards look like.
 */
import { useColorScheme } from 'frappe-ui'
import { __ } from '../../data/translation'

// The previews must show a light card as light while the app is painted dark, so their colours
// are deliberately literal instead of themed. Everything outside the preview frame is tokens.
const OPTIONS = [
  { value: 'light', label: __('Light'), frames: ['light'] },
  { value: 'dark', label: __('Dark'), frames: ['dark'] },
  { value: 'system', label: __('System'), frames: ['light', 'dark'] },
]

const { colorScheme, setColorScheme } = useColorScheme()
</script>

<template>
  <fieldset class="flex flex-col gap-2">
    <legend class="sr-only">{{ __('Appearance') }}</legend>

    <div class="flex flex-col items-stretch gap-3 sm:flex-row">
      <label
        v-for="option in OPTIONS"
        :key="option.value"
        class="group flex-1 cursor-pointer"
      >
        <input
          type="radio"
          name="appearance"
          class="peer sr-only"
          :value="option.value"
          :checked="colorScheme === option.value"
          @change="setColorScheme(option.value)"
        />

        <span
          class="block overflow-hidden rounded-5 border transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-outline-gray-3"
          :class="colorScheme === option.value ? 'border-outline-gray-5' : 'border-outline-gray-2'"
        >
          <!-- The mock window: a title bar, a rail and a few lines of content. One frame for
               light and dark, two side by side for system. -->
          <span class="flex h-20 bg-gray-100" aria-hidden="true">
            <span
              v-for="frame in option.frames"
              :key="frame"
              class="flex flex-1 flex-col gap-1 overflow-hidden p-2"
            >
              <span
                class="flex flex-1 flex-col gap-1 rounded-sm p-1.5"
                :class="frame === 'dark' ? 'bg-gray-900' : 'bg-white'"
              >
                <span class="flex gap-0.5">
                  <span class="size-1 rounded-full bg-red-400" />
                  <span class="size-1 rounded-full bg-amber-400" />
                  <span class="size-1 rounded-full bg-green-400" />
                </span>
                <span
                  v-for="line in 3"
                  :key="line"
                  class="h-1 rounded-full"
                  :class="frame === 'dark' ? 'bg-gray-600' : 'bg-gray-300'"
                />
              </span>
            </span>
          </span>

          <span
            class="flex items-center justify-between gap-2 border-t border-outline-gray-2 px-3 py-2"
          >
            <span class="truncate text-base text-ink-gray-7">{{ option.label }}</span>

            <!-- A tick, not a heavier ring: the chosen card has to say so at a glance. -->
            <span
              v-if="colorScheme === option.value"
              class="lucide-circle-check-big size-4 shrink-0 text-ink-gray-8"
              aria-hidden="true"
            />
            <span
              v-else
              class="size-3.5 shrink-0 rounded-full border border-outline-gray-3"
              aria-hidden="true"
            />
          </span>
        </span>
      </label>
    </div>
  </fieldset>
</template>
