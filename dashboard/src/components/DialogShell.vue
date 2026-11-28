<script setup>
/**
 * The frame every dialog in the product flows shares: a centred frappe-ui Dialog from `sm`, a
 * frappe-ui BottomSheet below it. Both keep the title and the header slot above the body and the
 * footer slot in view, so a long form never hides its buttons. The shell owns no close policy: it
 * only asks to close through `update:open`, and the caller decides (FormDialog asks before it
 * drops typed work, ImportDialog says a run keeps going).
 */
import { computed, ref, watch } from 'vue'
import { BottomSheet, Button, Dialog } from 'frappe-ui'
import { DialogTitle } from 'reka-ui'
import { useIsMobile } from '../utils/useIsMobile'

const props = defineProps({
  title: { type: String, required: true },
  size: { type: String, default: 'xl' },
  // `top` pins a tall, step-by-step dialog under the window's top edge, so it does not jump as
  // each step's body changes height.
  position: { type: String, default: 'center' },
  // Escape and a click outside (and, on a phone, a swipe down) ask to close.
  dismissible: { type: Boolean, default: true },
  // `desktop`: the × shows next to the title from `sm` only, because a sheet's footer always has
  // Cancel. `always`: a phone gets one too, in the sheet's corner, for a flow whose footer has no
  // way out. `none`: the buttons are the only way out.
  closeButton: { type: String, default: 'desktop' },
  closeDisabled: { type: Boolean, default: false },
  // A confirm reads as one block; a form's footer is set off from the fields above it.
  footerDivider: { type: Boolean, default: true },
  // Marks the body for frappe-ui Dialog's open focus: its first control takes focus instead of
  // the ×. Desktop only: a sheet focuses itself, so a phone's keyboard stays down until a tap.
  focusBody: { type: Boolean, default: false },
})

const open = defineModel('open', { type: Boolean, required: true })

const isMobile = useIsMobile()

// Mounted from the moment it opens until its close animation ends, not for the app's lifetime.
// frappe-ui's Dialog keeps its scroll container in <body> even while closed, so a dialog mounted
// early (a confirm, a "New collection" over Add product) is already in <body> when the one under
// it opens, and that one's aria-hidden sweep hides it: the dialog on top would show but be gone
// from the accessibility tree. Created at open, it is never swept.
const rendered = ref(open.value)
watch(open, (value) => {
  if (value) rendered.value = true
})

function onAfterLeave() {
  if (!open.value) rendered.value = false
}

// Dialog's own frame takes this much of the window (its py-4 + my-8 centred, or the 2rem top
// padding + py-4 + my-8 pinned to the top); the panel fits in the rest, so the footer stays on
// screen and only the body scrolls. dvh, not vh: on a phone vh is the height with the address
// bar hidden, which would push the footer off.
const PANEL_HEIGHTS = {
  center: 'max-h-[calc(100dvh-6rem)]',
  top: 'max-h-[calc(100dvh-8rem)]',
}

const showDesktopClose = computed(() => props.closeButton !== 'none')
const showSheetClose = computed(() => props.closeButton === 'always')

function requestClose() {
  if (!props.closeDisabled) open.value = false
}

const desktopBody = ref(null)
const sheetBody = ref(null)

// A caller whose body changes in place, such as a step flow, scrolls back to the top through
// this. From `sm` the body is its own scroll box; on a phone the scroller is the sheet's region,
// the parent this shell's markup is slotted into.
function scrollToTop() {
  const scroller = isMobile.value ? sheetBody.value?.parentElement : desktopBody.value
  scroller?.scrollTo({ top: 0 })
}

defineExpose({ scrollToTop })
</script>

<template>
  <BottomSheet
    v-if="rendered && isMobile"
    v-model:open="open"
    :title="props.title"
    :dismissible="props.dismissible"
    @after-leave="onAfterLeave"
  >
    <!-- The sheet's own scroll region holds all of this, so the header and the footer are pinned
         with sticky rather than taken out of the flow: a short sheet still hugs its content.
         z-20 keeps them over body content that is itself positioned, such as OptionSizeGrid's
         z-10 sticky column. -->
    <div v-if="$slots.header" class="sticky top-0 z-20 bg-surface-base px-4 pb-3 text-center">
      <slot name="header" />
    </div>
    <div ref="sheetBody" class="px-4 pb-5" :class="{ 'pt-1': !$slots.header }">
      <slot />
    </div>
    <!-- pb: the home-indicator inset on a notched phone, or 1rem where it is smaller (the same
         rule as frappe-ui's MobileNav). -->
    <div
      v-if="$slots.footer"
      class="sticky bottom-0 z-20 bg-surface-base px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3"
      :class="{ 'border-t border-outline-gray-1': props.footerDivider }"
    >
      <!-- A thumb needs a taller target than a pointer: frappe-ui's lg is 40px. -->
      <slot name="footer" button-size="lg" />
    </div>
    <!-- The sheet's DialogContent is `fixed`, so it is this button's containing block and the
         scroll region (not positioned) does not clip it: the × stays in the corner while the body
         scrolls. -->
    <Button
      v-if="showSheetClose"
      class="absolute end-3 top-3"
      variant="ghost"
      icon="lucide-x"
      :aria-label="__('Close')"
      :disabled="props.closeDisabled"
      @click="requestClose"
    />
  </BottomSheet>

  <Dialog
    v-else-if="rendered"
    v-model:open="open"
    :size="props.size"
    :position="props.position"
    :padding-top="props.position === 'top' ? '2rem' : undefined"
    bare
    :dismissible="props.dismissible"
    @after-leave="onAfterLeave"
  >
    <div class="flex flex-col" :class="PANEL_HEIGHTS[props.position]">
      <div class="px-6 pb-4 pt-5">
        <div class="flex items-start gap-3">
          <!-- reka's DialogTitle carries the id the dialog's aria-labelledby points at. -->
          <DialogTitle class="min-w-0 flex-1 text-2xl-semibold text-ink-gray-8">{{ props.title }}</DialogTitle>
          <Button
            v-if="showDesktopClose"
            class="-mt-0.5"
            variant="ghost"
            icon="lucide-x"
            :aria-label="__('Close')"
            :disabled="props.closeDisabled"
            @click="requestClose"
          />
        </div>
        <slot name="header" />
      </div>

      <div ref="desktopBody" v-scroll-fade class="min-h-0 flex-1 overflow-y-auto px-6 pb-6" :autofocus="props.focusBody">
        <slot />
      </div>

      <div
        v-if="$slots.footer"
        class="px-6"
        :class="props.footerDivider ? 'border-t border-outline-gray-1 py-4' : 'pb-6'"
      >
        <slot name="footer" button-size="sm" />
      </div>
    </div>
  </Dialog>
</template>
