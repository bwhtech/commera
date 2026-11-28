import { __ } from '../data/translation'
import { askConfirm } from './confirmDialog'

// A route guard has to answer with a value: this resolves true when the merchant chose to go on,
// false when they chose to stay (Keep editing, Esc, or a click outside). It draws the app's own
// ConfirmDialog rather than frappe-ui's `dialog.confirm`, whose imperative host stores the
// component reactively (a Vue warning) and draws the message outside a DialogDescription (a reka
// warning) on every guard.
export function confirmLeave(title, message, confirmLabel = __('Leave', null, 'Leave the page')) {
  return askConfirm({ title, message, confirmLabel, cancelLabel: __('Keep editing') })
}
