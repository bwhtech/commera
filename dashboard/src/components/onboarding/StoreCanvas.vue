<script setup>
/**
 * The storefront being built, as a sketch: each onboarding step turns one more dashed ghost into
 * the real piece — name, hero, button, products.
 */
import { computed } from 'vue'
import { storeProducts } from '../../data/onboarding'
import { priceRange } from '../../data/format'
import { CATEGORIES, SAMPLE_PRODUCTS, draft } from '../../ia/onboarding'
import { STEP_INDEX } from '../../ia/onboardingSteps'

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
    heroIcon: 'right-12 top-6 size-40',
    heroLine: 'text-5xl',
    button: 'px-5 py-2 text-sm',
    grid: '-mx-3 grid-cols-4 gap-4 p-3',
    caption: 'text-xs',
    tileIcon: 'size-7',
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
    heroIcon: 'right-3 top-3 size-20',
    heroLine: 'text-2xl',
    button: 'px-3.5 py-1 text-2xs',
    grid: 'grid-cols-2 gap-2',
    caption: 'text-2xs',
    tileIcon: 'size-5',
  },
}

// Listed rather than computed per index: Tailwind only generates class names it can read.
const STAGGER = ['delay-0', 'delay-75', 'delay-150', 'delay-200']

const size = computed(() => (props.mobile ? SIZES.mobile : SIZES.desktop))
const category = computed(() => CATEGORIES.find((option) => option.value === draft.storeCategory))
const storeName = computed(() => draft.storeName.trim())
const isTyping = computed(() => props.stage === STEP_INDEX.store)
const hasButton = computed(() => props.stage >= STEP_INDEX.brand)

const isSample = computed(() => !storeProducts.value.length)
const products = computed(() => {
  if (!isSample.value) {
    return storeProducts.value.map((product) => ({
      key: product.name,
      title: product.title,
      image: product.image,
      price: product.price_from == null ? '' : priceRange(product.price_from, product.price_to),
    }))
  }
  return (SAMPLE_PRODUCTS[draft.storeCategory] ?? []).map((icon) => ({ key: icon, icon }))
})
const showProducts = computed(() => (props.stage >= STEP_INDEX.products || !isSample.value) && products.value.length)

const perks = computed(() =>
  [
    { icon: 'lucide-banknote', on: draft.codEnabled },
    { icon: 'lucide-user-round', on: draft.allowGuestCheckout },
  ].filter((perk) => perk.on),
)

// Ring width, not colour, is what changes: box-shadow interpolates between widths, so moving the
// focus from one area to the next cross-fades instead of jumping.
const ring = (area) => (props.focus === area && !props.mobile ? 'ring-1 ring-inset ring-outline-gray-4' : 'ring-0')

// The owner's brand colour is data, not styling, so it is the one value bound inline.
const accent = computed(() => (draft.primaryColor ? { backgroundColor: draft.primaryColor } : null))
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
        enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
        enter-from-class="scale-90 opacity-0 motion-reduce:scale-100"
        leave-active-class="transition-opacity duration-150"
        leave-to-class="opacity-0"
      >
        <img v-if="draft.brandLogo" :src="draft.brandLogo" alt="" class="w-auto object-contain" :class="size.logo" />
      </Transition>
      <span v-if="storeName" class="truncate" :class="[size.name, look.heading]">
        {{ storeName
        }}<span
          v-if="isTyping"
          class="ml-px inline-block w-0.5 bg-surface-gray-10 align-middle motion-safe:animate-pulse"
          :class="size.caret"
        />
      </span>
      <span v-else class="h-2.5 rounded-full" :class="[look.tile, mobile ? 'w-14' : 'w-24']" />

      <div class="ml-auto flex items-center" :class="size.icons">
        <Transition
          enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
          enter-from-class="translate-x-1 opacity-0 motion-reduce:translate-x-0"
          leave-active-class="transition-opacity duration-150"
          leave-to-class="opacity-0"
        >
          <div
            v-if="focus === 'selling' && !mobile && perks.length"
            class="flex items-center gap-2.5 rounded-full px-3 py-1 text-ink-gray-5"
            :class="look.tile"
          >
            <span v-for="perk in perks" :key="perk.icon" :class="perk.icon" class="size-3.5" aria-hidden="true" />
          </div>
        </Transition>
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
        v-if="category"
        key="hero"
        class="relative flex flex-1 overflow-hidden transition-[background-color,border-radius,box-shadow] duration-500 ease-out-strong"
        :class="[size.hero, look.hero, look.radius, ring('theme')]"
      >
        <span :class="[category.icon, size.heroIcon]" class="absolute opacity-5" aria-hidden="true" />
        <h2 class="relative max-w-md font-medium leading-none tracking-tight" :class="[size.heroLine, look.heading]">
          {{ category.hero }}
        </h2>
        <Transition
          enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
          enter-from-class="translate-y-1.5 opacity-0 motion-reduce:translate-y-0"
        >
          <span
            v-if="hasButton"
            class="relative shrink-0 transition-[background-color,border-radius] duration-500 ease-out-strong"
            :class="[size.button, look.button, accent ? 'text-ink-base dark:text-ink-gray-9' : 'bg-surface-gray-10 text-ink-base']"
            :style="accent"
          >
            <!-- Brand colours run dark, so their label stays light: ink-base is white in light mode, and
                 under a dark look's data-theme the dark: variant swaps in the light end of the scale. -->
            Shop
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

    <section
      class="grid shrink-0 rounded-4 transition-shadow duration-300 ease-out-strong"
      :class="[size.grid, ring('products')]"
    >
      <template v-if="showProducts">
        <TransitionGroup
          appear
          enter-active-class="transition-[opacity,transform] duration-500 ease-out-strong"
          enter-from-class="translate-y-3 scale-[0.97] opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100"
        >
          <div
            v-for="(product, position) in products.slice(0, 4)"
            :key="product.key"
            :class="[STAGGER[position], { 'opacity-50': isSample }]"
          >
            <div
              class="flex aspect-[4/5] items-center justify-center overflow-hidden text-ink-gray-5"
              :class="[look.tile, look.radius]"
            >
              <img v-if="product.image" :src="product.image" alt="" class="size-full object-cover" />
              <span v-else :class="[product.icon || 'lucide-package', size.tileIcon]" class="opacity-60" aria-hidden="true" />
            </div>
            <div class="mt-1.5 flex items-baseline justify-between gap-2" :class="size.caption">
              <span v-if="product.title" class="truncate">{{ product.title }}</span>
              <span v-else class="h-1.5 w-3/5 rounded-full" :class="look.tile" />
              <span v-if="product.price" class="shrink-0 tabular-nums text-ink-gray-5">{{ product.price }}</span>
            </div>
          </div>
        </TransitionGroup>
        <div
          v-for="rest in Math.max(0, 4 - products.length)"
          :key="`rest-${rest}`"
          class="aspect-[4/5] border-2 border-dashed border-outline-gray-2"
          :class="look.radius"
        />
      </template>
      <template v-else>
        <div
          v-for="ghost in 4"
          :key="`ghost-${ghost}`"
          class="aspect-[4/5] border-2 border-dashed border-outline-gray-2"
          :class="look.radius"
        />
      </template>
    </section>
  </div>
</template>
