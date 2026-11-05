import { computed } from 'vue'
import { StorageSerializers, useStorage } from '@vueuse/core'
// Like cloudBilling.js, the Cloud Settings SDK calls Frappe's cloud_settings proxy itself.
import { getDomains } from '@frappe/cloud-sdk/api'
import { cloudContext } from './cloudBilling'
import { describeDomains } from './home'

export const isCloudDomainsAvailable = cloudContext.enabled === true

const CACHE_MS = 10 * 60 * 1000

const cached = useStorage('commera:cloud-domains', null, undefined, { serializer: StorageSerializers.object })

export const customDomain = computed(() =>
  isCloudDomainsAvailable ? describeDomains(cached.value?.domains) : null,
)

export async function refreshDomains() {
  try {
    cached.value = { domains: await getDomains(), fetchedAt: Date.now() }
  } catch (error) {
    console.warn('[commera] could not read the Frappe Cloud domains', error)
    cached.value = { domains: null, fetchedAt: Date.now() }
  }
}

export function loadDomains() {
  if (!isCloudDomainsAvailable) return
  if (Date.now() - (cached.value?.fetchedAt ?? 0) >= CACHE_MS) refreshDomains()
}
