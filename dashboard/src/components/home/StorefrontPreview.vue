<script setup>
import { ref, watch } from 'vue'
import { Skeleton } from 'frappe-ui'

const props = defineProps({
  live: { type: Boolean, default: false },
  url: { type: String, required: true },
  host: { type: String, required: true },
  image: { type: String, default: null },
})

const loaded = ref(false)
const failed = ref(false)
watch(
  () => props.image,
  () => {
    loaded.value = false
    failed.value = false
  },
)
</script>

<template>
  <div class="relative w-full sm:w-[30rem]">
    <a
      :href="url"
      target="_blank"
      rel="noopener"
      class="group relative block overflow-hidden rounded-6 border border-outline-gray-2 bg-surface-base shadow-lg transition-transform duration-200 ease-out-strong active:scale-[0.99] motion-reduce:transition-none hover:-translate-y-0.5"
      :aria-label="live ? 'View your storefront' : 'Preview your storefront'"
    >
      <div class="flex items-center gap-1.5 border-b border-outline-gray-1 bg-surface-gray-1 px-3 py-2">
        <span v-for="dot in 3" :key="dot" class="size-2 rounded-full bg-surface-gray-4" />
        <div class="mx-auto flex min-w-0 items-center gap-1 rounded-full bg-surface-base px-3 py-0.5 text-2xs text-ink-gray-5">
          <span class="size-2.5 shrink-0" :class="live ? 'lucide-globe' : 'lucide-lock'" aria-hidden="true" />
          <span class="truncate">{{ host }}</span>
        </div>
        <span class="w-8" />
      </div>

      <!-- A saved image, never a live frame: the thumbnail is captured once from the editor's preview
           page, which carries no tracking, so Home stays light and never counts as a storefront visit.
           The placeholder sits underneath, so a slow, missing or broken image leaves a store-shaped
           skeleton rather than an empty box. 18rem is the thumbnail's 16:10 at 30rem wide; the
           phone's shorter box crops it from the top. -->
      <div class="relative h-52 overflow-hidden sm:h-72">
        <div class="absolute inset-0 flex flex-col gap-3 p-4" aria-hidden="true">
          <div class="flex items-center justify-between">
            <Skeleton class="h-3 w-20 rounded-full" />
            <Skeleton class="h-3 w-12 rounded-full" />
          </div>
          <Skeleton class="h-24 w-full rounded-4 sm:h-32" />
          <div class="grid flex-1 grid-cols-4 gap-3">
            <Skeleton v-for="tile in 4" :key="tile" class="h-full rounded-4" />
          </div>
        </div>
        <img
          v-if="image && !failed"
          :src="image"
          alt=""
          decoding="async"
          class="absolute inset-0 size-full object-cover object-top transition-opacity duration-300 ease-out-strong motion-reduce:transition-none"
          :class="loaded ? 'opacity-100' : 'opacity-0'"
          @load="loaded = true"
          @error="failed = true"
        />
      </div>

      <div
        class="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-focus-visible:opacity-100 group-hover:opacity-100"
      >
        <span class="flex items-center gap-1.5 rounded-full bg-surface-base px-3 py-1.5 text-sm text-ink-gray-8 shadow-md">
          {{ live ? 'View store' : 'Preview store' }}
          <span class="lucide-arrow-up-right size-3.5" aria-hidden="true" />
        </span>
      </div>
    </a>

    <!-- Colours cross-fade while the label swaps out-in, so publishing reads as one change, not two. -->
    <div
      class="absolute -bottom-3.5 left-1/2 flex -translate-x-1/2 items-center rounded-full border px-3 py-1 text-sm shadow-md transition-colors duration-200"
      :class="live ? 'border-outline-green-2 bg-surface-green-2 text-ink-green-7' : 'border-transparent bg-surface-gray-9 text-ink-base'"
    >
      <Transition
        mode="out-in"
        enter-active-class="transition-[opacity,transform] duration-200 ease-out-strong"
        enter-from-class="scale-95 opacity-0 motion-reduce:scale-100"
        leave-active-class="transition-opacity duration-100 ease-out-strong"
        leave-to-class="opacity-0"
      >
        <span :key="live ? 'live' : 'private'" class="flex items-center gap-1.5">
          <span v-if="live" class="size-2 rounded-full bg-surface-green-7" />
          <span v-else class="lucide-lock size-3" aria-hidden="true" />
          {{ live ? 'Live' : 'Private' }}
        </span>
      </Transition>
    </div>
  </div>
</template>
