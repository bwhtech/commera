// The onboarding funnel, named as Frappe's setup wizard names its own, so one funnel reads Frappe,
// Raven and Commera alike (docs/telemetry.md, "First-run onboarding").
//
// The second deliberate exception to "one door to the server", beside cloudBilling.js: `left_setup`
// is sent as the page closes, and only fetch's `keepalive` outlives the page; useCall has no such
// option. The server keeps only known events and values before anything reaches Pulse.
import { methodUrl } from './api'
import { bootValue } from './boot'

// get_boot's `telemetry.enabled`: a site with telemetry off sends no request at all.
const isEnabled = () => bootValue('telemetry', {})?.enabled === true

// Best effort: a failure is ignored, and an event is lost if the page is gone before it is sent.
export function sendSetupEvent(event, properties = {}, { keepalive = false } = {}) {
  if (!isEnabled()) return
  fetch(methodUrl('onboarding.record_setup_event'), {
    method: 'POST',
    keepalive,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': bootValue('csrf_token', ''),
    },
    body: JSON.stringify({ event, properties }),
  }).catch(() => {})
}
