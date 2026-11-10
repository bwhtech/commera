// The pure half of data/cloudBilling.js, kept apart so `node --test` can import it: the other
// half imports the Cloud SDK.
import { __ } from './translation.js'

const URGENT_DAYS = 3

function endsInTitle(daysLeft) {
  if (daysLeft <= 0) return __('Your trial ends today')
  if (daysLeft === 1) return __('Your trial ends tomorrow')
  return __('Your trial ends in {0} days', [daysLeft])
}

function deletionNotice(deletesOn) {
  if (!deletesOn) return __('Choose a plan to keep using your store.')
  // A date-only string parses as UTC midnight, so it is formatted in UTC to keep the same day.
  const date = new Date(deletesOn).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' })
  return __('Your store will be deleted on {0}. Choose a plan to keep it.', [date])
}

// `trial` is Frappe Cloud's BillingTrial (from getBilling). An ended trial cannot be dismissed:
// the store is on its way to deletion, so the card stays until a plan is chosen.
export function getTrialNotice(trial) {
  if (!trial) return null
  if (trial.state === 'Ended') {
    return {
      theme: 'red',
      title: __('Your trial has ended'),
      description: deletionNotice(trial.deletes_on),
      actionLabel: __('Choose a plan'),
      dismissible: false,
    }
  }
  if (trial.held) {
    return {
      theme: 'amber',
      title: __('Your plan is over your spending limit'),
      description: __('Raise the limit or choose a smaller plan to end your trial.'),
      actionLabel: __('Manage billing'),
      dismissible: true,
    }
  }
  return {
    theme: trial.days_left <= URGENT_DAYS ? 'amber' : 'gray',
    title: endsInTitle(trial.days_left),
    description: __('Choose a plan to keep your store after the trial.'),
    actionLabel: __('Choose a plan'),
    dismissible: true,
  }
}
