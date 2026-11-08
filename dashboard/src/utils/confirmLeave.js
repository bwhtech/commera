import { dialog } from 'frappe-ui'

// A route guard has to answer with a value, and frappe-ui's confirm answers with callbacks: this
// resolves true when the merchant chose to go on, false when they chose to stay (Cancel, Esc, or a
// click outside).
export function confirmLeave(title, message, confirmLabel = 'Leave') {
  return new Promise((resolve) => {
    dialog.confirm({
      title,
      message,
      theme: 'red',
      confirmLabel,
      onConfirm: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}
