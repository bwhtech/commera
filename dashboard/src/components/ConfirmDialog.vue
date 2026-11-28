<script setup>
/**
 * The app's one "are you sure" (asked through utils/confirmDialog.js, usually by confirmLeave): a
 * title, one sentence, the safe answer and a red one. Mounted once in App.vue so a route guard can
 * ask from anywhere, including over an open dialog.
 */
import { Button } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import DialogShell from './DialogShell.vue'
import { confirmState, settleConfirm } from '../utils/confirmDialog'
</script>

<template>
  <DialogShell
    :open="confirmState.open"
    :title="confirmState.title"
    size="sm"
    close-button="none"
    :footer-divider="false"
    @update:open="(open) => open || settleConfirm(false)"
  >
    <!-- DialogDescription gives the dialog the aria-describedby reka checks for. -->
    <DialogDescription class="text-p-base text-ink-gray-7 max-sm:text-center">
      {{ confirmState.message }}
    </DialogDescription>
    <template #footer="{ buttonSize }">
      <!-- The safe answer comes first, so reka's open focus lands on it rather than on the red one. -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:justify-end">
        <Button :size="buttonSize" :label="confirmState.cancelLabel" @click="settleConfirm(false)" />
        <Button :size="buttonSize" variant="solid" theme="red" :label="confirmState.confirmLabel" @click="settleConfirm(true)" />
      </div>
    </template>
  </DialogShell>
</template>
