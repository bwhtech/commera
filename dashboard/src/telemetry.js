// Product telemetry. docs/telemetry.md is the only definition of an event's name and properties.
//
// The browser never talks to Pulse. Every event posts to Commera's own record_event, which passes
// on only the events and values the spec lists, adds the shared properties, and sends nothing when
// telemetry is off. A second deliberate exception to "one door to the server", beside
// data/cloudBilling.js: `left_setup` goes out as the page closes, and only fetch's `keepalive`
// outlives the page; useCall has no such option.
import { methodUrl } from './data/api'
import { bootValue } from './data/boot'

// get_boot's `telemetry` key. A site with telemetry off sends no request at all.
const config = bootValue('telemetry', {}) ?? {}

// Frappe's own rule for desk and its SPAs: page views only while a site is new.
const NEW_SITE_DAYS = 15

// Best effort: a failure is ignored, and an event is lost if the page is gone before it is sent.
export function capture(event, properties = {}, { keepalive = false } = {}) {
  if (config.enabled !== true) return
  fetch(methodUrl('telemetry.record_event'), {
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

// One `pageview` per navigation, with the matched route pattern (`/products/:id`), never the URL.
export function trackPageviews(router) {
  if (config.enabled !== true || config.site_age > NEW_SITE_DAYS) return
  let lastFullPath = ''
  router.afterEach((to) => {
    if (to.fullPath === lastFullPath) return
    lastFullPath = to.fullPath
    capture('pageview', { route: to.matched.at(-1)?.path || 'unmatched' })
  })
}
