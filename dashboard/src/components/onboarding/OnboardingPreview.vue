<script setup>
/** The store as it builds: a desktop browser, with a phone over its corner on wide screens. */
import { useEntrance } from '../../utils/reveal'
import StoreCanvas from './StoreCanvas.vue'

defineProps({
  focus: { type: String, default: '' },
  stage: { type: Number, default: 0 },
  look: { type: Object, required: true },
})

const storeHost = window.location.host

// The desktop settles first; the phone follows, sliding out from behind the desktop's side.
const entered = useEntrance()
</script>

<template>
  <div class="relative size-full max-h-[700px] max-w-[960px]">
    <div
      class="absolute inset-0 flex flex-col overflow-hidden rounded-6 border border-outline-gray-2 bg-surface-base shadow-xl transition-[opacity,transform] delay-75 duration-700 ease-out-strong xl:bottom-16 xl:right-48"
      :class="entered ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-3.5 scale-[0.985] opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100'"
    >
      <div class="flex h-9 shrink-0 items-center gap-1.5 border-b border-outline-gray-1 bg-surface-gray-1 px-3">
        <span v-for="dot in 3" :key="dot" class="size-2.5 rounded-full bg-surface-gray-4" />
        <div class="mx-auto flex w-64 items-center justify-center gap-1.5 rounded-4 bg-surface-base px-3 py-1 text-xs text-ink-gray-5">
          <span class="lucide-lock size-3" aria-hidden="true" />
          <span class="truncate">{{ storeHost }}</span>
        </div>
        <!-- Balances the three dots so the address bar sits in the true centre. -->
        <span class="w-10" />
      </div>
      <div class="min-h-0 flex-1" :data-theme="look.dark ? 'dark' : undefined">
        <StoreCanvas :focus="focus" :stage="stage" :look="look" />
      </div>
    </div>

    <div
      class="absolute bottom-0 right-0 hidden h-[470px] w-[230px] transition-[opacity,transform] delay-500 duration-1000 ease-out-strong xl:block"
      :class="entered ? 'translate-x-0 scale-100 opacity-100' : '-translate-x-16 scale-95 opacity-0 motion-reduce:translate-x-0 motion-reduce:scale-100'"
    >
      <!-- The bezel is a device, not app chrome, so it stays dark in a light dashboard. It is a
           sibling of the screen, not its parent: frappe-ui's tokens have no light scope to undo a
           dark one, so a light store could not render inside it. -->
      <div data-theme="dark" class="absolute inset-0 rounded-[40px] bg-surface-base shadow-2xl ring-1 ring-inset ring-outline-gray-2" />
      <div class="absolute inset-[7px] flex flex-col overflow-hidden rounded-[33px] bg-surface-base" :data-theme="look.dark ? 'dark' : undefined">
        <div class="relative flex h-8 shrink-0 items-center justify-between px-5 text-2xs font-semibold text-ink-gray-9">
          <span>9:41</span>
          <span data-theme="dark" class="absolute left-1/2 top-2 h-[18px] w-[70px] -translate-x-1/2 rounded-full bg-surface-base" />
          <span class="flex items-center gap-1">
            <span class="lucide-signal size-2.5" aria-hidden="true" />
            <span class="lucide-wifi size-2.5" aria-hidden="true" />
            <span class="lucide-battery-full size-3" aria-hidden="true" />
          </span>
        </div>
        <div class="min-h-0 flex-1">
          <StoreCanvas :focus="focus" :stage="stage" :look="look" mobile />
        </div>
        <span class="mx-auto mb-1.5 h-1 w-20 shrink-0 rounded-full bg-surface-gray-10 opacity-40" />
      </div>
    </div>
  </div>
</template>
