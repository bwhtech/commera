import { computed } from 'vue'
import { StorageSerializers, useStorage } from '@vueuse/core'
// The one deliberate exception to "one door to the server": the Cloud Settings SDK calls
// frappe.integrations.frappe_providers.cloud_settings.* itself, and Frappe proxies those to
// the bench's Pilot. Commera has no endpoint in between to route them through.
import { getBilling } from '@frappe/cloud-sdk/api'
import { bootValue } from './boot'
import { getTrialNotice } from './trialNotice'

// Days left change once a day, and each read goes through Pilot to Frappe Cloud.
const CACHE_MS = 6 * 60 * 60 * 1000

// get_boot always carries this key (devBoot too), and frappe's get_boot_context already
// answers `enabled: false` unless the site is a Frappe Cloud v2 site and the user a System
// Manager, so availability is decided on the server with no request of our own.
export const cloudContext = bootValue('cloud_settings', { enabled: false })
export const isCloudBillingAvailable = cloudContext.enabled === true

const cached = useStorage('commera:cloud-billing', null, undefined, { serializer: StorageSerializers.object })

export const billing = computed(() => (isCloudBillingAvailable ? cached.value?.billing : undefined))
export const trialNotice = computed(() => getTrialNotice(billing.value?.trial))

export async function refreshBilling() {
  try {
    cached.value = { billing: await getBilling(), fetchedAt: Date.now() }
  } catch (error) {
    // The card is a quiet hint, not a screen: a Pilot outage must not toast over every page.
    // A self-hosted Pilot writes the same credentials Frappe Cloud does but has no Cloud behind
    // it, so it refuses every read. The failure is cached like an answer, so such a bench asks
    // again only when the cache runs out, not on every page load.
    console.warn('[commera] could not read the Frappe Cloud billing', error)
    cached.value = { billing: null, fetchedAt: Date.now() }
  }
}

let isLoaded = false

export function loadBillingOnce() {
  if (isLoaded || !isCloudBillingAvailable) return
  isLoaded = true
  if (Date.now() - (cached.value?.fetchedAt ?? 0) >= CACHE_MS) refreshBilling()
}
