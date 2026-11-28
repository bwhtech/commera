import { reactive } from 'vue'

// The one confirm the app draws (ConfirmDialog, mounted once in App.vue). A question asked while
// another is still open answers the old one "no" first: a caller always gets an answer, and two
// sheets never stack.
export const confirmState = reactive({
  open: false,
  title: '',
  message: '',
  confirmLabel: '',
  cancelLabel: '',
  resolve: null,
})

export function askConfirm({ title, message, confirmLabel, cancelLabel }) {
  settleConfirm(false)
  return new Promise((resolve) => {
    Object.assign(confirmState, { open: true, title, message, confirmLabel, cancelLabel, resolve })
  })
}

// Every way out (the two buttons, Escape, a click outside, a swipe) lands here, once.
export function settleConfirm(confirmed) {
  const resolve = confirmState.resolve
  confirmState.resolve = null
  confirmState.open = false
  resolve?.(confirmed)
}

// The app's one single-field question (PromptDialog, mounted once in App.vue), for the menu
// actions that ask for one value. `submit(value)` does the write and resolves true when it took;
// the dialog stays open, value kept, on a refusal, which the write has already toasted.
export const promptState = reactive({
  open: false,
  title: '',
  message: '',
  label: '',
  type: 'text',
  options: [],
  value: '',
  // What the field opened with: the dialog is dirty, and asks before closing, once `value` differs.
  initialValue: '',
  confirmLabel: '',
  submit: null,
  loading: false,
})

export function askValue({ title, message = '', label, type = 'text', options = [], value = '', confirmLabel, submit }) {
  Object.assign(promptState, {
    open: true, title, message, label, type, options, value, initialValue: value, confirmLabel, submit, loading: false,
  })
}

// Compared as text: a number field hands back a string as soon as it is edited, so 5 and "5" are
// the same value, and typing a digit and deleting it leaves the dialog clean again.
export function isPromptDirty() {
  return String(promptState.value ?? '') !== String(promptState.initialValue ?? '')
}

export async function submitPrompt() {
  if (promptState.loading || !promptState.submit) return
  promptState.loading = true
  try {
    if (await promptState.submit(promptState.value)) promptState.open = false
  } finally {
    promptState.loading = false
  }
}
