<script setup>
/**
 * The frame every dialog in the product flows shares: a centred frappe-ui Dialog from `sm`, a
 * frappe-ui BottomSheet below it. Both keep the title and the header slot above the body and the
 * footer slot in view, so a long form never hides its buttons. The shell owns no close policy: it
 * only asks to close through `update:open`, and the caller decides (FormDialog asks before it
 * drops typed work, ImportDialog says a run keeps going).
 */
import { computed, defineComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BottomSheet, Button, Dialog } from 'frappe-ui'
import { DialogTitle, injectDialogRootContext } from 'reka-ui'
import { useDialogLayer } from '../utils/dialogLayers'
import { endStaleSheetGestures } from '../utils/sheetGesture'
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
  // Cancel. `always`: a phone gets one too, on the sheet's title row, for a flow whose footer has
  // no way out. `none`: the buttons are the only way out.
  closeButton: { type: String, default: 'desktop' },
  closeDisabled: { type: Boolean, default: false },
  // A confirm reads as one block; a form's footer is set off from the fields above it.
  footerDivider: { type: Boolean, default: true },
  // Marks the body for frappe-ui Dialog's open focus: its first control takes focus instead of
  // the ×. Desktop only: a sheet focuses itself, so a phone's keyboard stays down until a tap.
  focusBody: { type: Boolean, default: false },
  // Where focus goes once the dialog has closed, when the control that opened it is gone. reka
  // returns focus to the element focused before the open; a "New collection" opened from the
  // Collection select's list footer was opened by a button that left with the list, so reka's
  // return lands on <body> and the form under it loses the merchant's place. A function that moves
  // focus to the control to go back to.
  returnFocus: { type: Function, default: null },
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
  if (open.value) return
  rendered.value = false
  restoreFocus()
}

// After the leave animation reka has already made its own return, so this only steps in when that
// return found nothing to land on: a focus the merchant moved elsewhere is left alone. A frame later,
// because the content element (and the focus it held) is removed on the render after after-leave.
function restoreFocus() {
  if (!props.returnFocus) return
  requestAnimationFrame(() => {
    const active = document.activeElement
    if (active && active !== document.body) return
    props.returnFocus()
  })
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

// A dialog opened over this one (a "Discard changes?", a "New collection") covers it.
const isCovered = useDialogLayer(open)

// Made inert while it still holds focus, the covered dialog would drop focus to <body> before the
// one on top takes it, and that one would then hand focus back to <body> when it closes. So the
// covered dialog waits for focus to leave it first.
function whenFocusLeaves(element, callback) {
  if (!element.contains(document.activeElement)) {
    callback()
    return null
  }
  const stop = () => document.removeEventListener('focusin', onFocusIn)
  function onFocusIn() {
    if (element.contains(document.activeElement)) return
    stop()
    callback()
  }
  document.addEventListener('focusin', onFocusIn)
  return stop
}

/*
 * Corrects the dialog's content element where neither frappe-ui's Dialog nor its BottomSheet lets a
 * caller set an attribute. It renders inside them, because reka's dialog context (which knows the
 * content element and the description id) can only be read below DialogRoot, and this shell sits
 * above it. Recheck each rule when frappe-ui changes these components.
 * - aria-describedby: BottomSheet hard-codes it to undefined (its way of telling reka a sheet has no
 *   description), which also drops the one every shell here draws, so a sheet lost "Color of Cotton
 *   tee" or "What you entered here is not saved." Linked only when the description is in the DOM.
 * - aria-modal: reka does not set it, so the tree reported the dialog as non-modal.
 * - aria-label: BottomSheet labels a sheet without its `title` prop "Bottom sheet". This shell draws
 *   its own DialogTitle, which names the sheet through aria-labelledby, so the stale label goes.
 * - inert while covered: reka hides everything outside the top dialog, except that aria-hidden keeps
 *   every aria-live region and its ancestors exposed, and FormDialog's footer reason line is one. So
 *   the form under a confirm stayed in the accessibility tree. Inert takes it out until the top one
 *   closes; it is removed as soon as the top one starts closing, so its focus return lands.
 * - a sheet's leftover mouse gesture: ended before a hover can drag it (utils/sheetGesture.js).
 */
const ContentAttributes = defineComponent({
  props: {
    covered: { type: Boolean, default: false },
    // A BottomSheet: its mouse gestures are guarded (see utils/sheetGesture.js).
    sheet: { type: Boolean, default: false },
  },
  setup(attributeProps) {
    const context = injectDialogRootContext()
    const content = ref(null)
    let stopWaiting = null
    let stopGestureGuard = null

    function cover(covered) {
      stopWaiting?.()
      stopWaiting = null
      const element = content.value
      if (!element) return
      if (covered) stopWaiting = whenFocusLeaves(element, () => (element.inert = true))
      else element.inert = false
    }

    onMounted(async () => {
      // reka hands its content element to the context in its own onMounted, which runs after this
      // child's.
      await nextTick()
      const element = context.contentElement?.value
      // Until reka has a content element it holds a placeholder comment (nodeType 8), or nothing.
      if (element?.nodeType !== 1) return
      content.value = element
      element.setAttribute('aria-modal', 'true')
      if (element.hasAttribute('aria-labelledby')) element.removeAttribute('aria-label')
      if (!element.hasAttribute('aria-describedby') && document.getElementById(context.descriptionId)) {
        element.setAttribute('aria-describedby', context.descriptionId)
      }
      cover(attributeProps.covered)
      if (attributeProps.sheet) stopGestureGuard = endStaleSheetGestures(element)
    })
    watch(() => attributeProps.covered, cover)
    onBeforeUnmount(() => {
      cover(false)
      stopGestureGuard?.()
    })

    return () => null
  },
})
</script>

<template>
  <!-- No `title` prop: the sheet draws its own, in the sticky header below, so the × can sit on
       the title's row and the description can sit close under it. BottomSheet's title lives in
       its grab-handle block, out of reach of both. -->
  <BottomSheet
    v-if="rendered && isMobile"
    v-model:open="open"
    :dismissible="props.dismissible"
    @after-leave="onAfterLeave"
  >
    <ContentAttributes :covered="isCovered" sheet />
    <!-- The sheet's own scroll region holds all of this, so the header and the footer are pinned
         with sticky rather than taken out of the flow: a short sheet still hugs its content.
         z-20 keeps them over body content that is itself positioned, such as OptionSizeGrid's
         z-10 sticky column. The header's description (mt-1 in the slot) sits 4px under the title
         and 16px (pb-4) above the body, so it reads as the title's, not the body's. -->
    <div class="sticky top-0 z-20 bg-surface-base px-4 pb-4 text-center">
      <!-- pt-2 and the type are BottomSheet's own title, so a sheet reads the same with or
           without the ×. The × is in the row, top-aligned with the first line of the title
           (28px beside a 27px line), and 16px in from the edge, clear of the 36px corner. A
           same-size spacer on the start side keeps the title centred on the sheet. -->
      <div class="flex items-start gap-2 pt-2">
        <span v-if="showSheetClose" class="size-7 shrink-0" aria-hidden="true" />
        <DialogTitle class="min-w-0 flex-1 text-3xl-semibold text-ink-gray-9">{{ props.title }}</DialogTitle>
        <Button
          v-if="showSheetClose"
          class="shrink-0"
          variant="ghost"
          icon="lucide-x"
          :aria-label="__('Close')"
          :disabled="props.closeDisabled"
          @click="requestClose"
        />
      </div>
      <slot name="header" />
    </div>
    <div ref="sheetBody" class="px-4 pb-5">
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
    <ContentAttributes :covered="isCovered" />
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
