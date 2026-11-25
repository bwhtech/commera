<script setup>
/**
 * The storefront being built, as a sketch: each onboarding step turns one more dashed ghost into
 * the real piece — name, hero, button, products.
 */
import { computed } from 'vue'
import { draft } from '../../ia/onboarding'
import { STEP_INDEX } from '../../ia/onboardingSteps'
import commeraLogo from '../../assets/commera.svg'

const props = defineProps({
  focus: { type: String, default: '' },
  stage: { type: Number, default: 0 },
  mobile: { type: Boolean, default: false },
  look: { type: Object, required: true },
})

const SIZES = {
  desktop: {
    frame: 'gap-6 px-8 pb-8 pt-5',
    header: '-mx-3 px-3 py-2',
    logo: 'h-7 max-w-32',
    name: 'text-lg-semibold',
    caret: 'h-4',
    icons: 'gap-4',
    icon: 'size-4',
    hero: 'min-h-48 items-end justify-between p-8',
    heroIcon: 'end-12 top-6 size-40',
    heroLine: 'text-5xl',
    button: 'px-5 py-2 text-sm',
    grid: '-mx-3 grid-cols-4 gap-4 p-3',
  },
  mobile: {
    frame: 'gap-3 px-3 pb-4 pt-1',
    header: 'px-1 py-1.5',
    logo: 'h-5 max-w-16',
    name: 'text-sm-semibold',
    caret: 'h-3',
    icons: 'gap-2.5',
    icon: 'size-3',
    hero: 'min-h-32 flex-col items-start justify-end gap-3 p-4',
    heroIcon: 'end-3 top-3 size-20',
    heroLine: 'text-2xl',
    button: 'px-3.5 py-1 text-2xs',
    grid: 'grid-cols-2 gap-2',
  },
}

const size = computed(() => (props.mobile ? SIZES.mobile : SIZES.desktop))
const storeName = computed(() => draft.storeName.trim())
const isTyping = computed(() => props.stage === STEP_INDEX.store)
const hasButton = computed(() => props.stage >= STEP_INDEX.store)

// Ring width, not colour, is what changes: box-shadow interpolates between widths, so moving the
// focus from one area to the next cross-fades instead of jumping.
const ring = (area) => (props.focus === area && !props.mobile ? 'ring-1 ring-inset ring-outline-gray-4' : 'ring-0')
</script>

<template>
  <div
    class="flex h-full flex-col overflow-hidden bg-surface-base text-ink-gray-9 transition-colors duration-500 ease-out-strong"
    :class="size.frame"
  >
    <header
      class="flex shrink-0 items-center gap-2.5 rounded-4 transition-shadow duration-300 ease-out-strong"
      :class="[size.header, ring('brand')]"
    >
      <Transition
        mode="out-in"
        enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
        enter-from-class="scale-90 opacity-0 motion-reduce:scale-100"
        leave-active-class="transition-opacity duration-150"
        leave-to-class="opacity-0"
      >
        <img :key="draft.brandLogo" :src="draft.brandLogo || commeraLogo" alt="" class="w-auto object-contain" :class="size.logo" />
      </Transition>
      <span v-if="storeName" class="truncate" :class="[size.name, look.heading]">
        {{ storeName
        }}<span
          v-if="isTyping"
          class="ms-px inline-block w-0.5 bg-surface-gray-10 align-middle motion-safe:animate-pulse"
          :class="size.caret"
        />
      </span>
      <span v-else class="h-2.5 rounded-full" :class="[look.tile, mobile ? 'w-14' : 'w-24']" />

      <div class="ms-auto flex items-center" :class="size.icons">
        <Transition enter-active-class="transition-opacity duration-500 ease-out-strong" enter-from-class="opacity-0">
          <div v-if="stage >= STEP_INDEX.store" class="flex items-center" :class="size.icons">
            <span class="lucide-search" :class="size.icon" aria-hidden="true" />
            <span class="lucide-shopping-bag" :class="size.icon" aria-hidden="true" />
          </div>
        </Transition>
      </div>
    </header>

    <Transition
      mode="out-in"
      enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
      enter-from-class="scale-[0.97] opacity-0 motion-reduce:scale-100"
      leave-active-class="transition-opacity duration-150"
      leave-to-class="opacity-0"
    >
      <section
        v-if="storeName"
        key="hero"
        class="relative flex flex-1 overflow-hidden transition-[background-color,border-radius,box-shadow] duration-500 ease-out-strong"
        :class="[size.hero, look.hero, look.radius]"
      >
        <span :class="size.heroIcon" class="lucide-shopping-bag absolute opacity-5" aria-hidden="true" />
        <h2 class="relative max-w-md font-medium leading-none tracking-tight" :class="[size.heroLine, look.heading]">
          {{ __('Made with care.') }}
        </h2>
        <Transition
          enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
          enter-from-class="translate-y-1.5 opacity-0 motion-reduce:translate-y-0"
        >
          <span
            v-if="hasButton"
            class="relative shrink-0 bg-surface-gray-10 text-ink-base transition-[border-radius] duration-500 ease-out-strong"
            :class="[size.button, look.button]"
          >
            {{ __('Shop') }}
          </span>
        </Transition>
      </section>
      <div
        v-else
        key="ghost"
        class="flex-1 border-2 border-dashed border-outline-gray-2"
        :class="[look.radius, mobile ? 'min-h-32' : 'min-h-48']"
      />
    </Transition>

    <section class="grid shrink-0" :class="size.grid">
      <div
        v-for="ghost in 4"
        :key="`ghost-${ghost}`"
        class="aspect-[4/5] border-2 border-dashed border-outline-gray-2"
        :class="look.radius"
      />
    </section>
  </div>
</template>
